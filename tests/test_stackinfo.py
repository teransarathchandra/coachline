import json, os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import stackinfo  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: f.write(text)


class Detect(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.TemporaryDirectory(); self.d = self.tmp.name
    def tearDown(self): self.tmp.cleanup()

    def test_npm_public_names_with_major_versions_runtime_first(self):
        write(os.path.join(self.d, "package.json"), json.dumps({"name": "secret-project",
              "dependencies": {"next": "^15.1.0", "react": "19.0.0", "@acme/internal-ui": "1.0.0", "@tanstack/react-query": "~5.2",
                               "local-lib": "file:../lib", "shared": "workspace:*"},
              "devDependencies": {"@types/node": "22", "tailwindcss": "4.0.0", "my-fork": "github:me/fork"}}))
        self.assertEqual(stackinfo.detect(self.d), ["node", "next@15", "react@19", "@tanstack/react-query@5", "tailwindcss@4"])

    def test_python_pyproject_and_requirements(self):
        write(os.path.join(self.d, "pyproject.toml"), '[project]\nname = "secret"\nrequires-python = ">=3.11"\n'
              'dependencies = [\n  "Django>=5.0",\n  "psycopg[binary]==3.2.1",\n  "mylib @ file:///x",\n]\n')
        write(os.path.join(self.d, "requirements.txt"), "fastapi==0.115.0\n-e ./local\ngit+https://github.com/me/x\n# comment\nrequests\n")
        self.assertEqual(stackinfo.detect(self.d), ["python", "django@5", "psycopg@3", "fastapi@0", "requests"])

    def test_poetry_go_and_cargo(self):
        write(os.path.join(self.d, "py", "pyproject.toml"), '[tool.poetry.dependencies]\npython = "^3.12"\nflask = "^3.0"\n'
              'mine = { path = "../mine" }\n\n[tool.poetry.group.dev.dependencies]\npytest = "^8"\n')
        self.assertEqual(stackinfo.detect(os.path.join(self.d, "py")), ["python", "flask@3"])
        write(os.path.join(self.d, "go", "go.mod"), "module example.com/secret\n\ngo 1.22\n\nrequire github.com/acme/private v1.0.0\n")
        self.assertEqual(stackinfo.detect(os.path.join(self.d, "go")), ["go@1.22"])
        write(os.path.join(self.d, "rs", "Cargo.toml"), '[package]\nname = "secret"\n\n[dependencies]\n'
              'tokio = { version = "1.40", features = ["full"] }\nserde = "1.0"\nmine = { path = "../mine" }\n')
        self.assertEqual(stackinfo.detect(os.path.join(self.d, "rs")), ["rust", "tokio@1", "serde@1"])

    def test_walks_up_to_the_manifest_but_not_past_the_repository_root(self):
        write(os.path.join(self.d, "package.json"), json.dumps({"dependencies": {"vue": "3.4.0"}}))
        sub = os.path.join(self.d, "src", "components"); os.makedirs(sub)
        self.assertEqual(stackinfo.detect(sub), ["node", "vue@3"])
        repo = os.path.join(self.d, "inner"); os.makedirs(os.path.join(repo, ".git"))
        self.assertEqual(stackinfo.detect(repo), [])

    def test_missing_folders_and_broken_files_give_nothing(self):
        self.assertEqual(stackinfo.detect(os.path.join(self.d, "gone")), [])
        self.assertEqual(stackinfo.detect(""), [])
        self.assertEqual(stackinfo.detect(None), [])
        write(os.path.join(self.d, "package.json"), "{not json")
        self.assertEqual(stackinfo.detect(self.d), [])

    def test_long_dependency_lists_are_capped_and_keep_the_language(self):
        write(os.path.join(self.d, "package.json"), json.dumps({"dependencies": {f"lib{i}": f"{i}.0.0" for i in range(1, 41)}}))
        got = stackinfo.detect(self.d)
        self.assertEqual((len(got), got[0], got[1]), (12, "node", "lib1@1"))


if __name__ == "__main__":
    unittest.main()
