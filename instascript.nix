{
  lib,
  python3,
  ffmpeg,
  yt-dlp,
}:
python3.pkgs.buildPythonApplication {
  pname = "instascript";
  version = "0.2.0";

  src = lib.cleanSourceWith {
    src = ./.;
    filter = path: type:
      let
        base = baseNameOf path;
      in
      !(lib.hasPrefix ".venv" base)
      && base != ".local"
      && !(lib.hasPrefix ".env" base)
      && base != ".git"
      && base != ".claude"
      && base != "__pycache__"
      && base != "result"
      && !(lib.hasSuffix ".pyc" path);
  };

  pyproject = true;
  build-system = [ python3.pkgs.setuptools ];

  propagatedBuildInputs = with python3.pkgs; [
    faster-whisper
    requests
    httpx
  ];
  # Nixpkgs supplies mutually compatible PyAV/faster-whisper versions; the pip
  # deployment lock pins its own tested pair independently.
  pythonRelaxDeps = [ "faster-whisper" "av" "httpx" ];

  # yt-dlp (URL resolution) + ffmpeg (audio normalization) must be on PATH at
  # runtime. Nix python wrappers don't freeze the caller's PATH, so we pin a
  # wrapper that guarantees them regardless of the user's environment.
  postInstall = ''
    for command in instascript sonaweft; do
      wrapProgram $out/bin/$command \
        --prefix PATH : ${lib.makeBinPath [ ffmpeg yt-dlp ]} \
        --set-default HF_HUB_DISABLE_XET 1
    done
  '';

  meta = with lib; {
    description = "Sonaweft: audio to source-linked notes (faster-whisper, optional DeepSeek review, built-in dedup)";
    homepage = "https://github.com/m-amir-gomaa/ig_intel";
    license = licenses.mit;
    mainProgram = "sonaweft";
    platforms = platforms.linux;
  };
}
