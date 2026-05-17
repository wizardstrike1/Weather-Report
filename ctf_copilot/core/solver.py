"""The autonomous solving loop.

observe → ask Claude → validate → permission/approval gate → execute → record →
summarise → repeat. Runs on a worker thread; communicates via the EventBus.
Controls: step_once(), start_auto(), pause(), stop(). User answers / approvals
are delivered through thread-safe setters.
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass

from ..browser.dom_summarizer import compact_observation
from ..browser.playwright_session import PlaywrightSession
from ..core.config import KNOWLEDGE_DB, AppConfig
from ..core.events import EventBus, EventType
from ..core.knowledge import KnowledgeBase, Lesson
from ..core.permissions import PermissionDenied, Permissions
from ..core.project import (
    STATUS_AWAITING,
    STATUS_INCOMPLETE,
    STATUS_INPUT_NEEDED,
    STATUS_SOLVED,
    Project,
)
from ..llm.claude_client import ClaudeClient
from ..llm.conversation_memory import ConversationMemory
from ..llm.prompt_builder import build_user_message
from ..llm.token_budget import TokenBudget
from ..llm.tool_router import LLMResponse, parse_llm_response
from ..tools import file_analyzer, web_research
from ..tools.registry import ToolRegistry
from ..tools.runner import ToolRunner
from ..writeup import generator

NOISY_APPROVAL_MSG = "This action is noisy/active and needs your approval."


@dataclass
class SolverControls:
    paused: bool = False
    stop: bool = False
    afk: bool = False  # auto-resolve every user prompt (no interaction)


class Solver:
    def __init__(self, project: Project, config: AppConfig, bus: EventBus) -> None:
        self.project = project
        self.config = config
        self.bus = bus
        self.perms = Permissions(project.root, config.allowed_domains)
        self.registry = ToolRegistry(config.tool_paths)
        self.runner = ToolRunner(self.registry, self.perms, project.tool_outputs_dir)
        self.llm = ClaudeClient(
            config.anthropic_api_key,
            config.model,
            config.max_tokens_per_step,
            cli_command=config.claude_cli_command,
        )
        bus.log(f"LLM backend: {self.llm.backend}")
        self.memory = ConversationMemory(config.summarize_after_n_messages)
        self.budget = TokenBudget(
            config.token_budget_per_session, config.max_tokens_per_step
        )
        try:
            self.kb: KnowledgeBase | None = KnowledgeBase(KNOWLEDGE_DB)
            bus.log(f"Knowledge base: {self.kb.count()} prior lesson(s)")
        except Exception as e:  # never block solving on the KB
            self.kb = None
            bus.log(f"Knowledge base unavailable: {e}", "error")
        self.session: PlaywrightSession | None = None
        self.controls = SolverControls(afk=config.afk_mode)
        self._flag_re = self._compile_flags()
        self._pending_answer: str | None = None
        self._pending_approval: bool | None = None
        self._ev = threading.Event()
        self._nudge = ""          # corrective hint appended after a bad reply
        self._parse_fails = 0     # consecutive unparseable LLM replies
        self._last_sig: str | None = None  # last action signature
        self._repeat = 0          # consecutive identical actions

    def _compile_flags(self) -> re.Pattern[bytes]:
        joined = "|".join(f"(?:{r})" for r in self.config.flag_regexes)
        return re.compile(joined.encode(), re.I)

    # ---- session ---------------------------------------------------------
    def ensure_browser(self) -> PlaywrightSession:
        if self.session is None:
            # Per-project profile dir: Chromium locks its user-data-dir, so a
            # shared profile would make multiple instances/projects collide.
            profile = self.project.root / "browser-profile"
            self.session = PlaywrightSession(
                profile_dir=profile,
                downloads_dir=self.project.downloads_dir,
                screenshots_dir=self.project.screenshots_dir,
                headless=self.config.headless,
            )
            self.session.start()
            self.bus.log("Browser session started")
        return self.session

    def shutdown(self) -> None:
        if self.session:
            self.session.stop()
            self.session = None
        if self.kb:
            self.kb.close()
            self.kb = None

    # ---- user interaction bridges ---------------------------------------
    def provide_answer(self, text: str) -> None:
        self._pending_answer = text
        self._ev.set()

    def provide_approval(self, ok: bool) -> None:
        self._pending_approval = ok
        self._ev.set()

    def _wait_user(self) -> None:
        self._ev.clear()
        while not self._ev.wait(0.25):
            if self.controls.stop:
                return

    def _set_status(self, status: str) -> None:
        """Persist the project status and let the GUI refresh its sidebar."""
        self.project.set_status(status)
        self.bus.publish(EventType.SOLVER_STATE, state=status)

    def _publish_tokens(self, ptok: int, ctok: int) -> None:
        try:
            total = int(self.project.state.get_meta("tokens_spent", "0") or 0)
        except ValueError:
            total = 0
        total += ptok + ctok
        self.project.state.set_meta("tokens_spent", str(total))
        self.bus.publish(
            EventType.TOKENS,
            step=ptok + ctok,
            session=self.budget.spent,
            session_limit=self.budget.session_limit,
            project_total=total,
            backend=self.llm.backend,
        )

    def _record_lesson(self, flag: str) -> None:
        """Distil what was learned (especially struggles) into the shared
        knowledge base so future challenges benefit."""
        if not (self.kb and self.config.enable_learning):
            return
        try:
            st = self.project.state
            acts = list(reversed(st.recent_actions(limit=120)))
            worked = [
                f"{a['kind']}: {a['summary']}" for a in acts if a["success"]
            ]
            pitfalls = [
                f"{a['kind']}: {a['summary']}"
                for a in acts if not a["success"]
            ]
            facts = st.facts()[-10:]
            hyps = [n["content"] for n in st.notes("hypothesis")]
            struggled = " (solved after working through earlier failures)" if \
                pitfalls else ""
            solution = (
                "WHAT WORKED:\n- " + "\n- ".join(worked[-15:] or ["(n/a)"])
                + "\n\nPITFALLS / DEAD-ENDS TO AVOID:\n- "
                + "\n- ".join(pitfalls[-12:] or ["(none)"])
                + (f"\n\nFLAG FORMAT: {flag.split('{')[0]}{{...}}" if flag else "")
            )
            self.kb.add_lesson(Lesson(
                category=self.project.category or "unknown",
                title=f"{self.project.name}{struggled}",
                problem=(self.project.state.get_meta("user_context")
                         or " | ".join(facts))[:1500],
                solution=solution[:4000],
                tags=" ".join(
                    {a["kind"] for a in acts}
                    | {self.project.category.lower()}
                ),
            ))
            self.bus.log("Recorded a lesson to the knowledge base")
        except Exception as e:  # learning must never break a solved run
            self.bus.log(f"Could not record lesson: {e}", "error")

    def _ask(
        self,
        question: str,
        *,
        approval: bool = False,
        status: str = STATUS_INPUT_NEEDED,
        **extra,
    ) -> None:
        """Set the given waiting status, ask, and block until answered.
        Auto-restores 'incomplete' afterward only if still in that waiting
        status (the caller resolves awaiting-confirmation outcomes itself)."""
        self.project.state.add_note(question, "question")

        if self.controls.afk:
            # AFK: never block. Approvals -> approve (the "keep going" choice).
            # Free-text -> tell the model to proceed autonomously.
            if approval:
                self._pending_approval = True
            else:
                self._pending_answer = (
                    "AFK MODE: no user is available. Do NOT ask the user "
                    "anything. Proceed fully autonomously using your tools "
                    "(write scripts with file.write, run them with tool.run "
                    "python, inspect files, use the browser). Make the most "
                    "reasonable assumption and continue to the flag."
                )
            self.bus.publish(
                EventType.ASK_USER, question=question, approval=approval,
                afk_auto=True, **extra,
            )
            self.bus.log(f"[AFK] auto-resolved: {question[:90]}")
            self._set_status(STATUS_INCOMPLETE)
            return

        self._set_status(status)
        self.bus.publish(
            EventType.ASK_USER, question=question, approval=approval, **extra
        )
        self._wait_user()
        if self.project.status == status:
            self._set_status(STATUS_INCOMPLETE)

    # ---- the loop --------------------------------------------------------
    def run(self, auto: bool, max_steps: int | None = None) -> None:
        max_steps = max_steps or self.config.max_solver_steps
        last_obs: dict = {}
        for step in range(1, max_steps + 1):
            if self.controls.stop:
                self.bus.publish(EventType.SOLVER_STATE, state="stopped")
                return
            while self.controls.paused and not self.controls.stop:
                self.bus.publish(EventType.SOLVER_STATE, state="paused")
                self._ev.wait(0.3)
            self.bus.publish(EventType.SOLVER_STATE, state="thinking", step=step)

            try:
                resp = self._think(last_obs)
            except Exception as e:  # unexpected backend error
                self.bus.publish(EventType.ERROR, message=f"think failed: {e}")
                resp = None

            if resp is None:
                # An unparseable / failed reply must NOT kill the loop.
                self._parse_fails += 1
                if self._parse_fails >= 3:
                    self._parse_fails = 0
                    self._ask(
                        "The reasoning backend returned no valid JSON action "
                        "3 times in a row. Reply with a concrete next step in "
                        "plain text (e.g. \"inspect downloads/decode.py\"), or "
                        "type 'stop' to halt; or set an ANTHROPIC_API_KEY in "
                        "Settings and reply 'continue'."
                    )
                    if self._pending_answer is not None:
                        self.project.state.add_fact(
                            f"User guidance: {self._pending_answer}"
                        )
                        self._pending_answer = None
                # Even in "Step once" mode, keep retrying think within this
                # invocation instead of silently no-op'ing the click. The
                # bounded loop + the >=3 ask_user above are the safety net.
                if self.controls.stop:
                    self.bus.publish(EventType.SOLVER_STATE, state="stopped")
                    return
                self.bus.publish(
                    EventType.SOLVER_STATE, state="retrying", step=step
                )
                continue
            self._parse_fails = 0

            # repeated-action guard: stop the agent spinning on one action
            sig = (
                f"{resp.action.type}|{resp.action.name}|"
                + json.dumps(resp.action.args, sort_keys=True)
            )
            self._repeat = self._repeat + 1 if sig == self._last_sig else 0
            self._last_sig = sig
            if self._repeat >= 3:
                self._repeat = 0
                self._ask(
                    f"The agent is stuck repeating "
                    f"'{resp.action.type} {resp.action.name}' with the same "
                    f"args. Reply with a specific instruction for what to do "
                    f"differently (plain text), or type 'stop' to halt."
                )
                if self._pending_answer is not None:
                    self.project.state.add_fact(
                        f"User guidance: {self._pending_answer}"
                    )
                    self._pending_answer = None
                if not auto or self.controls.stop:
                    self.bus.publish(EventType.SOLVER_STATE, state="idle", step=step)
                    return
                continue

            self.bus.publish(
                EventType.LLM_ACTION,
                hypothesis=resp.hypothesis,
                thought=resp.thought_summary,
                action=resp.action.model_dump(),
                risk=resp.risk,
            )
            for n in resp.notes_to_save:
                self.project.state.add_note(n, "note")

            cont, last_obs = self._dispatch(resp)
            self.memory.record_turn(f"{resp.action.type} {resp.action.name}")
            if not cont or not auto:
                self.bus.publish(
                    EventType.SOLVER_STATE,
                    state="idle" if cont else "finished",
                    step=step,
                )
                return
        self.bus.publish(EventType.SOLVER_STATE, state="max_steps_reached")

    def _think(self, last_obs: dict) -> LLMResponse | None:
        snap = self.project.state.snapshot()
        delta = self.memory.observation_delta(last_obs) if last_obs else {}
        avail = [t["name"] for t in self.registry.availability() if t["available"]]
        lessons = []
        if self.kb and self.config.enable_learning:
            query = f"{self.project.name} {' '.join(snap.get('facts', [])[:5])}"
            lessons = self.kb.relevant(self.project.category, query, limit=5)
        msg = build_user_message(
            snap, delta, self.memory.digest_text(), avail,
            lessons=lessons,
            internet_research=self.config.allow_internet_research,
        )
        if self._nudge:
            msg += "\n\nIMPORTANT: " + self._nudge
        result = self.llm.complete(msg, self.budget)
        self._publish_tokens(result.prompt_tokens, result.completion_tokens)
        if not result.manual_mode:
            self.bus.log(
                f"LLM step: {result.prompt_tokens}+{result.completion_tokens} tok "
                f"(session spent {self.budget.spent})"
            )
        try:
            resp = parse_llm_response(result.raw_text)
            self._nudge = ""
            return resp
        except ValueError as e:
            # Return None (loop retries with a nudge) instead of raising and
            # killing the whole solve.
            self.bus.publish(
                EventType.ERROR, message=f"bad LLM JSON (will retry): {e}"
            )
            self._nudge = (
                "Your previous reply could not be parsed. Respond with ONLY a "
                "single JSON object matching the required schema — no prose, "
                "no markdown, no code fences."
            )
            return None

    # ---- action dispatch -------------------------------------------------
    def _dispatch(self, resp: LLMResponse) -> tuple[bool, dict]:
        a = resp.action
        st = self.project.state
        try:
            if a.type == "ask_user":
                q = a.args.get("question", "Need input.")
                self._ask(q)
                if self._pending_answer is not None:
                    st.add_fact(f"User answered: {self._pending_answer}")
                    self._pending_answer = None
                return True, {}

            if resp.needs_user_approval or self._is_noisy(a):
                self._ask(
                    f"Approve this action? {a.type} {a.name} {a.args}. "
                    f"Reply by clicking Approve to run it, or Deny to skip it.",
                    approval=True, action=a.model_dump(),
                )
                if not self._pending_approval:
                    self._pending_approval = None
                    st.add_action(a.type, "user denied approval", success=False)
                    return True, {}
                self._pending_approval = None

            if a.type.startswith("browser."):
                return True, self._do_browser(a)
            if a.type == "file.write":
                return True, self._do_file_write(a)
            if a.type in ("web.search", "web.fetch"):
                return True, self._do_research(a)
            if a.type == "file.inspect" or a.type == "file.extract":
                return True, self._do_file(a)
            if a.type == "tool.run":
                return True, self._do_tool(a)
            if a.type == "notes.add":
                st.add_note(a.args.get("content", ""), a.args.get("kind", "note"))
                return True, {}
            if a.type == "flag.submit_candidate":
                return self._do_flag(a), {}
            if a.type == "writeup.update":
                paths = generator.generate(self.project)
                self.bus.log(f"Writeup updated: {paths['markdown']}")
                return True, {}
            if a.type == "done":
                self._ask(
                    "The agent believes the challenge is solved. Confirm: "
                    "click Approve if it is genuinely solved (mark SOLVED), or "
                    "Deny to keep working.",
                    approval=True, status=STATUS_AWAITING,
                )
                if self._pending_approval:
                    self._pending_approval = None
                    self.project.set_solved(True)
                    self._record_lesson(flag="")
                    generator.generate(self.project)
                    self.bus.publish(EventType.SOLVER_STATE, state="solved")
                    return False, {}
                self._pending_approval = None
                st.add_fact("User says the challenge is NOT solved; continue.")
                self._set_status(STATUS_INCOMPLETE)
                return True, {}
        except PermissionDenied as e:
            self.bus.publish(EventType.ERROR, message=f"blocked: {e}")
            st.add_action(a.type, f"blocked: {e}", success=False)
            return True, {}
        except Exception as e:
            self.bus.publish(EventType.ERROR, message=f"action error: {e}")
            st.add_action(a.type, f"error: {e}", success=False)
            return True, {}
        return True, {}

    def _is_noisy(self, action) -> bool:
        if action.type != "tool.run":
            return False
        spec = self.registry.get(action.name)
        return bool(spec and spec.noisy)

    def _do_browser(self, a) -> dict:
        sess = self.ensure_browser()
        t = a.type.split(".", 1)[1]
        if t == "open_url":
            url = self.perms.check_url(a.args["url"])
            obs = sess.open_url(url)
            self.project.state.set_meta("url", url)
        elif t == "click":
            obs = sess.click(a.args.get("ref", a.name))
        elif t == "fill":
            obs = sess.fill(a.args["selector"], a.args.get("value", ""))
        elif t == "upload":
            raw = a.args.get("files", a.args.get("file", ""))
            files = [
                str(self.perms.resolve_in_workspace(p.strip(), must_exist=True))
                for p in raw.split(",")
                if p.strip()
            ]
            if not files:
                raise PermissionDenied("browser.upload requires 'files' arg")
            obs = sess.upload(a.args.get("selector", "input[type=file]"), files)
        elif t == "submit":
            obs = sess.submit(a.args.get("selector", "form"))
        elif t == "screenshot":
            path = sess.screenshot(a.args.get("name", "shot"))
            self.bus.publish(EventType.BROWSER_ACTION, action="screenshot", path=path)
            return {}
        elif t == "download":
            obs = sess.open_url(self.perms.check_url(a.args["url"]))
            d = sess.take_pending_download()
            if d:
                self.project.state.add_download(d["path"], d["source_url"], d["sha256"])
                self.bus.publish(EventType.DOWNLOAD, **d)
                self._scan_file_for_flags(d["path"])
        else:
            raise PermissionDenied(f"unknown browser action {t}")
        obs = compact_observation(obs)
        self._scan_text_for_flags(obs.get("visible_text", ""), obs.get("url", ""))
        self.project.state.add_action(a.type, f"{t} -> {obs.get('url','')}")
        self.bus.publish(EventType.PAGE_OBSERVED, observation=obs)
        return obs

    _TEXT_SUFFIXES = {
        ".py", ".txt", ".md", ".json", ".c", ".h", ".cpp", ".js", ".ts",
        ".sh", ".php", ".rb", ".go", ".java", ".rs", ".html", ".xml", ".yaml",
        ".yml", ".sql", ".pl", ".lua", ".asm", ".s", ".cfg", ".ini", ".env",
        ".enc", ".b64", ".pem", ".csv", ".log",
    }

    def _do_file(self, a) -> dict:
        src = (
            a.args.get("file")
            or a.args.get("path")
            or a.args.get("filename")
            or a.args.get("name")
            or a.name
        )
        if not src:
            raise PermissionDenied(
                "file.inspect/extract requires a 'file' arg: a path inside the "
                "project workspace, e.g. \"downloads/decode.py\". Available "
                f"downloads: {[r['path'] for r in self.project.state.downloads()]}"
            )
        path = self.perms.resolve_in_workspace(src, must_exist=True)
        res = file_analyzer.analyze(
            path,
            flag_pattern=self._flag_re,
            extract_to=self.project.artifacts_dir / path.stem
            if a.type == "file.extract"
            else None,
        )
        for fl in res.flag_candidates:
            self._add_flag(fl, f"file:{path.name}", 0.7)

        payload: dict = {"analysis": res.summary()}
        # Truncated strings are useless for reading source/config. For small
        # text-ish files, return the FULL content so the agent can reason about
        # code (this is what the decode.py case needed).
        try:
            size = path.stat().st_size
            looks_text = (
                "text" in res.file_type
                or path.suffix.lower() in self._TEXT_SUFFIXES
            )
            if size <= 65536 and looks_text:
                content = path.read_text("utf-8", "replace")
                payload["file_content"] = content[:16000]
                self.project.state.add_fact(
                    f"Full content of {path.name} ({size}B):\n{content[:6000]}"
                )
        except OSError:
            pass

        self.project.state.add_tool_output(
            "file_analyzer", str(path),
            res.summary() + (
                "\n[full source captured in facts]"
                if "file_content" in payload else ""
            ),
            "",
        )
        self.bus.publish(EventType.TOOL_RESULT, tool="file_analyzer",
                         summary=res.summary())
        return payload

    def _do_research(self, a) -> dict:
        if not self.config.allow_internet_research:
            raise PermissionDenied(
                "Internet research is disabled. Enable it in Settings "
                "('allow internet research') or solve from first principles."
            )
        mb = self.config.research_max_bytes
        if a.type == "web.search":
            q = a.args.get("query") or a.args.get("q") or a.name
            if not q:
                raise PermissionDenied("web.search requires a 'query' arg")
            out = web_research.search(q, max_bytes=mb)
            label, key = f"search: {q}", q
        else:
            url = a.args.get("url") or a.name
            if not url:
                raise PermissionDenied("web.fetch requires a 'url' arg")
            out = web_research.fetch(url, max_bytes=mb)
            label, key = f"fetch: {url}", url
        self.project.state.add_tool_output("web", label, out[:4000], "")
        self.project.state.add_action(a.type, label, success=True)
        self.bus.publish(EventType.TOOL_RESULT, tool=a.type, summary=out[:2000])
        return {"research": out[:4000], "query": key}

    def _do_file_write(self, a) -> dict:
        """Let the agent author its own scripts/payloads inside the workspace
        (then run them via tool.run python). Path is sandbox-confined; bare
        names land in artifacts/ so they don't clobber downloads."""
        rel = (
            a.args.get("file")
            or a.args.get("path")
            or a.args.get("filename")
            or a.name
        )
        if not rel:
            raise PermissionDenied(
                "file.write requires a 'file' arg (relative path, e.g. "
                "\"artifacts/solve.py\") and a 'content' arg."
            )
        if "/" not in rel and "\\" not in rel:
            rel = f"artifacts/{rel}"
        path = self.perms.resolve_in_workspace(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = a.args.get("content", "")
        path.write_text(content, "utf-8")
        rels = str(path.relative_to(self.project.root))
        self.project.state.add_action(
            "file.write", f"wrote {rels} ({len(content)}B)", success=True
        )
        self.project.state.add_fact(
            f"Authored {rels} ({len(content)}B). Run it with "
            f'tool.run python {{"file":"{rels}"}}.'
        )
        self.bus.publish(EventType.TOOL_RESULT, tool="file.write",
                         summary=f"wrote {rels} ({len(content)} bytes)")
        return {"written": rels, "bytes": len(content)}

    def _do_tool(self, a) -> dict:
        spec = self.registry.get(a.name)
        if spec and spec.requires_target and "target" in a.args:
            self.perms.check_url(a.args["target"]) if "://" in a.args["target"] \
                else self.perms.check_network_target(a.args["target"])
        res = self.runner.run(a.name, a.args, approved=True)
        self.project.state.add_tool_output(
            a.name, " ".join(res.argv), res.summary, str(res.log_path)
        )
        self.project.state.add_action("tool.run", f"{a.name} rc={res.returncode}",
                                       success=res.returncode == 0)
        self._scan_text_for_flags(res.summary, f"tool:{a.name}")
        self.bus.publish(EventType.TOOL_RESULT, tool=a.name,
                         summary=res.summary, returncode=res.returncode,
                         log_path=str(res.log_path))
        return {"tool_summary": res.summary}

    def _do_flag(self, a) -> bool:
        """Propose a candidate flag, then REQUIRE the user to confirm the CTF
        platform actually accepted it. Approve => solved. Deny => the flag is
        recorded as wrong and the solve loop continues."""
        value = a.args.get("value", "").strip()
        if not value:
            return True
        try:
            conf = float(a.args.get("confidence", 0.9) or 0.9)
        except ValueError:
            conf = 0.9
        self._add_flag(value, "llm", conf)

        self._ask(
            f"FLAG CONFIRMATION NEEDED.\nCandidate flag: {value}\n"
            f"Submit this on the CTF platform, then:\n"
            f"• click APPROVE if it was ACCEPTED (challenge -> SOLVED), or\n"
            f"• click DENY if it was REJECTED (I'll mark it wrong and keep "
            f"solving).",
            approval=True, status=STATUS_AWAITING, flag=value,
        )
        accepted = bool(self._pending_approval)
        self._pending_approval = None

        if accepted:
            self.project.state.mark_flag_submitted(value)
            self.project.set_solved(True)
            self._record_lesson(flag=value)
            generator.generate(self.project)
            self.bus.publish(EventType.SOLVER_STATE, state="solved", flag=value)
            return False

        # rejected -> keep going, and make sure the model does not retry it
        self.project.state.add_fact(
            f"Flag candidate {value!r} was REJECTED by the platform — it is "
            f"INCORRECT. Do not propose it again; keep solving."
        )
        self.project.state.add_action(
            "flag.submit_candidate", f"{value} rejected by platform",
            success=False,
        )
        self._set_status(STATUS_INCOMPLETE)
        return True

    # ---- flag scanning ---------------------------------------------------
    def _add_flag(self, value: str, source: str, conf: float) -> None:
        self.project.state.add_flag_candidate(value, source, conf)
        self.bus.publish(EventType.FLAG_CANDIDATE, value=value,
                         source=source, confidence=conf)

    def _scan_text_for_flags(self, text: str, source: str) -> None:
        for m in self._flag_re.finditer(text.encode("utf-8", "ignore")):
            self._add_flag(m.group().decode("utf-8", "ignore"), source, 0.6)

    def _scan_file_for_flags(self, path: str) -> None:
        try:
            res = file_analyzer.analyze(path, flag_pattern=self._flag_re)
            for fl in res.flag_candidates:
                self._add_flag(fl, f"download:{path}", 0.7)
        except Exception:
            pass
