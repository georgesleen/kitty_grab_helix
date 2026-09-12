{
  description = "kitty_grab_helix: helix-style keyboard selection for kitty";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "aarch64-darwin"
        "aarch64-linux"
        "x86_64-darwin"
        "x86_64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      pkgsFor = system: nixpkgs.legacyPackages.${system};
    in
    {
      # The kitten itself: the python modules kitty loads, in one store path.
      # Point kitty at ${kitty_grab_helix}/grab.py.
      packages = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        rec {
          default = kitty_grab_helix;
          kitty_grab_helix = pkgs.callPackage ./package.nix { };
        }
      );

      # For consumers who would rather have it in pkgs than reach into
      # packages.<system>.
      overlays.default = _final: prev: {
        kitty_grab_helix = prev.callPackage ./package.nix { };
      };

      checks = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          # The unit suites. The kitten's decision half imports no kitty code,
          # so the whole selection model runs here with no terminal.
          tests =
            pkgs.runCommand "kitty_grab_helix-tests"
              {
                nativeBuildInputs = [
                  pkgs.python3
                  pkgs.python3Packages.pytest
                ];
              }
              ''
                cp -r ${./.} source
                chmod -R +w source
                cd source
                pytest -q -p no:cacheprovider 2>&1 | tee "$out"
              '';

          lint = pkgs.runCommand "kitty_grab_helix-lint" { nativeBuildInputs = [ pkgs.ruff ]; } ''
            cp -r ${./.} source
            chmod -R +w source
            cd source
            ruff check --cache-dir "$TMPDIR/ruff" . 2>&1 | tee "$out"
          '';
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.gnumake
              pkgs.nixfmt-rfc-style
              pkgs.python3
              pkgs.python3Packages.pytest
              pkgs.ruff
            ];
          };
        }
      );
    };
}
