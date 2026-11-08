# Sourced by the hooks: find the repo's Python (venv first) and run local/ci.py with $CI_FLAGS.
# (Not "$@": a sourced script sees the hook's own arguments, e.g. pre-push gets "origin <url>".)
root="$(git rev-parse --show-toplevel)"
for py in "$root/.venv/bin/python" "$root/.venv/Scripts/python.exe" python3 python; do
  if command -v "$py" >/dev/null 2>&1 || [ -x "$py" ]; then PY="$py"; break; fi
done
if [ -z "$PY" ]; then echo "hook: no Python found; skipping checks" >&2; exit 0; fi
cd "$root" && "$PY" local/ci.py $CI_FLAGS
