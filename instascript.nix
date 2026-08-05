{
  lib,
  python3,
  ffmpeg,
  yt-dlp,
}:
python3.pkgs.buildPythonApplication {
  pname = "instascript";
  version = "0.1.0";

  src = lib.cleanSourceWith {
    src = ./.;
    filter = path: type:
      let
        base = baseNameOf path;
      in
      base != ".venv"
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
  ];

  # yt-dlp (URL resolution) + ffmpeg (audio normalization) must be on PATH at
  # runtime. Nix python wrappers don't freeze the caller's PATH, so we pin a
  # wrapper that guarantees them regardless of the user's environment.
  postInstall = ''
    wrapProgram $out/bin/instascript \
      --prefix PATH : ${lib.makeBinPath [ ffmpeg yt-dlp ]} \
      --set-default HF_HUB_DISABLE_XET 1
  '';

  meta = with lib; {
    description = "Reel/audio → local AI-verified transcripts (faster-whisper, optional DeepSeek review, built-in dedup)";
    homepage = "https://github.com/m-amir-gomaa/ig_intel";
    license = licenses.mit;
    mainProgram = "instascript";
    platforms = platforms.linux;
  };
}
