import asyncio
import unittest
from agi_runtime.tools.registry import ToolRegistry, discover_builtin_tools


class TestTools(unittest.TestCase):
    def setUp(self):
        self.reg = ToolRegistry.get_instance()
        discover_builtin_tools()

    def test_tools_registered(self):
        tools = self.reg.list_tools()
        self.assertGreaterEqual(len(tools), 17)

    def test_tool_schemas(self):
        schemas = self.reg.get_schemas()
        self.assertGreaterEqual(len(schemas), 17)
        for s in schemas:
            self.assertIn("name", s)
            self.assertIn("description", s)
            self.assertIn("input_schema", s)

    def test_python_exec(self):
        r = asyncio.run(self.reg.execute("python_exec", {"code": "print(2+2)"}))
        self.assertTrue(r.ok)
        self.assertIn("4", r.to_content())

    def test_file_read(self):
        r = asyncio.run(self.reg.execute("file_read", {"path": "README.md"}))
        self.assertTrue(r.ok)

    def test_unknown_tool(self):
        r = asyncio.run(self.reg.execute("nonexistent_tool", {}))
        self.assertFalse(r.ok)


if __name__ == '__main__':
    unittest.main()
