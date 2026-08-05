#!/usr/bin/env bash
# Resolve NixOS system libraries needed by pip-built wheels (PyAV/ctranslate2/
# onnxruntime link against glibc-family libs absent from the default linker
# path on NixOS). Sets LD_LIBRARY_PATH. Store paths resolved dynamically so a
# nix rebuild doesn't break the launcher.
#
# Usage: source bin/nixlibs.sh; export_instainfo_ld_library_path

export_instainfo_ld_library_path() {
    local lib d found=""
    for lib in libz.so.1 libstdc++.so.6 libgcc_s.so.1 libgomp.so.1; do
        d=$(find /nix/store -maxdepth 4 -name "$lib" 2>/dev/null |
            while read -r f; do
                # ELF64 magic: bytes 7f 45 4c 46 02 → trailing hex "02"
                # (head follows symlinks; broken links read empty → skipped)
                if [ "$(head -c 5 "$f" 2>/dev/null | od -An -tx1 | tr -d ' \n' | tail -c 2)" = "02" ]; then
                    dirname "$f"
                    break
                fi
            done)
        [ -n "$d" ] && found="$found${found:+:}$d"
    done
    export LD_LIBRARY_PATH="$found${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
}
