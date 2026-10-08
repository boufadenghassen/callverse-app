# models/

Trained models the app will load later (for example `emotion_v3_full.joblib`, or an `.h5` file).
This is the only folder where model files are allowed in git; everywhere else they are ignored.

* Name files `<task>_<version>.<ext>` and add a small `<same name>.json` next to each one:
  dataset, notebook version, metrics and date, so nobody has to guess what a file is.
* GitHub refuses files over 100 MB. For bigger models use Git LFS (`git lfs track "models/*.h5"`) or a GitHub Release.
* Train in `notebooks/`, then copy the finished file here. The notebooks write to `../models` by default.
