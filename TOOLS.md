# Supported Tools

Generated from the registry. Missing tools degrade gracefully — the built-in
Python analyzers still work. Install hints target Debian/Ubuntu & macOS (brew).

## crypto

| Tool | Noisy | Description | Install |
|------|-------|-------------|---------|
| hashcat |  | GPU password cracker | linux: apt install hashcat |
| john |  | Password cracker | linux: apt install john |
| name-that-hash |  | Hash identifier | linux: pipx install name-that-hash |
| openssl |  | Crypto toolkit | linux: apt install openssl |

## forensics

| Tool | Noisy | Description | Install |
|------|-------|-------------|---------|
| binwalk |  | Firmware/embedded file analysis | linux: apt install binwalk |
| bulk_extractor |  | Bulk feature extraction | linux: apt install bulk-extractor |
| exiftool |  | Metadata reader | linux: apt install libimage-exiftool-perl |
| foremost |  | File carving by header/footer | linux: apt install foremost |
| pdfinfo |  | PDF metadata | linux: apt install poppler-utils |
| qpdf |  | PDF transform | linux: apt install qpdf |
| tcpdump |  | PCAP reader | linux: apt install tcpdump |
| tshark |  | PCAP analysis | linux: apt install tshark |
| volatility3 |  | Memory forensics | linux: pipx install volatility3 |

## osint

| Tool | Noisy | Description | Install |
|------|-------|-------------|---------|
| dig |  | DNS lookup | linux: apt install dnsutils |
| nslookup |  | DNS lookup | linux: apt install dnsutils |
| whois |  | Domain registration | linux: apt install whois |

## pwn

| Tool | Noisy | Description | Install |
|------|-------|-------------|---------|
| ROPgadget |  | ROP gadget finder | linux: pipx install ROPgadget |
| checksec |  | Binary hardening check | linux: apt install checksec |
| one_gadget |  | libc one-gadget finder | linux: gem install one_gadget |
| patchelf |  | ELF interpreter patcher | linux: apt install patchelf |
| ropper |  | ROP gadget finder | linux: pipx install ropper |

## reverse

| Tool | Noisy | Description | Install |
|------|-------|-------------|---------|
| apktool |  | APK disassembler | linux: apt install apktool |
| jadx |  | APK/dex to Java | linux: apt install jadx |
| ltrace |  | Library call trace | linux: apt install ltrace |
| objdump |  | Disassembler | linux: apt install binutils |
| r2 |  | radare2 reverse engineering | linux: apt install radare2 |
| readelf |  | ELF reader | linux: apt install binutils |
| strace |  | Syscall trace | linux: apt install strace |
| upx |  | Executable packer | linux: apt install upx-ucl |

## shell

| Tool | Noisy | Description | Install |
|------|-------|-------------|---------|
| 7z |  | 7-Zip extract | linux: apt install p7zip-full |
| file |  | Identify file type by magic bytes | linux: apt install file; macos: brew install libmagic |
| hexdump |  | Canonical hex dump | linux: apt install bsdmainutils |
| jq |  | JSON processor | linux: apt install jq; macos: brew install jq |
| rg |  | Recursive regex search | linux: apt install ripgrep; macos: brew install ripgrep |
| strings |  | Extract printable strings | linux: apt install binutils; macos: brew install binutils |
| xxd |  | Hex dump | linux: apt install xxd |

## stego

| Tool | Noisy | Description | Install |
|------|-------|-------------|---------|
| outguess |  | Outguess stego | linux: apt install outguess |
| pngcheck |  | PNG integrity | linux: apt install pngcheck |
| steghide |  | JPEG/WAV stego | linux: apt install steghide |
| stegseek |  | Fast steghide cracker | linux: https://github.com/RickdeJager/stegseek |
| zsteg |  | PNG/BMP LSB stego | linux: gem install zsteg |

## web

| Tool | Noisy | Description | Install |
|------|-------|-------------|---------|
| curl |  | HTTP client | linux: apt install curl |
| feroxbuster | yes | Recursive content discovery | linux: apt install feroxbuster |
| ffuf | yes | Web fuzzer | linux: go install github.com/ffuf/ffuf/v2@latest |
| gobuster | yes | Directory brute force | linux: apt install gobuster |
| httpie |  | Friendly HTTP client | linux: pipx install httpie |
| nikto | yes | Web server scanner | linux: apt install nikto |
| nuclei | yes | Template scanner (disabled unless templates installed) | linux: go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest |
| sqlmap | yes | SQL injection tool (authorized CTF targets only) | linux: apt install sqlmap |
| wafw00f |  | WAF fingerprint | linux: pipx install wafw00f |

## Notes

- Noisy tools require explicit in-app approval before running.
- GUI tools (Ghidra, Burp, OWASP ZAP, Wireshark, sonic-visualiser,
  CyberChef) are launcher-style and tracked as TODO in registry.py.
- SecLists path is configured via Settings -> tool_paths (wordlist).