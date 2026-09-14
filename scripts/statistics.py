import pathlib
files = list(pathlib.Path(r"C:\Users\dnc\Documents\zdrojaky\carSelector").rglob("*.py"))
total_lines = sum(len(f.read_text(encoding="utf-8", errors="ignore").splitlines()) for f in files)
print(f"{len(files)} files, {total_lines} lines")