# The kitten as a store path. kitty adds the directory of the kitten it runs
# to sys.path, so the helix_* modules resolve as siblings of grab.py.
{
  lib,
  stdenvNoCC,
}:

stdenvNoCC.mkDerivation {
  dontBuild = true;
  dontConfigure = true;
  installPhase = ''
    runHook preInstall
    mkdir -p "$out"
    cp grab.py _grab_ui.py helix_motions.py helix_keymap.py helix_config.py "$out/"
    cp LICENSE README.md grab.conf.example "$out/"
    runHook postInstall
  '';
  meta = {
    description = "Helix-style keyboard selection and copy mode for kitty";
    homepage = "https://github.com/georgesleen/kitty_grab_helix";
    license = lib.licenses.gpl3Plus;
    platforms = lib.platforms.all;
  };
  pname = "kitty_grab_helix";
  src = ./.;
  version = "1.0.0";
}
