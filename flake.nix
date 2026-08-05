{
  description = "instaScript — reel/audio → local AI-verified transcripts";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = {
    self,
    nixpkgs,
  }: let
    systems = ["x86_64-linux" "aarch64-linux"];
    forAllSystems = nixpkgs.lib.genAttrs systems;
  in {
    packages = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
    in {
      instascript = pkgs.callPackage ./instascript.nix {};
      default = pkgs.callPackage ./instascript.nix {};
    });

    devShells = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
    in {
      default = pkgs.mkShell {
        packages = [
          pkgs.ffmpeg
          pkgs.yt-dlp
          pkgs.python3
        ];
      };
    });
  };
}
