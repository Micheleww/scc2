import unittest


class TestCmdSafety(unittest.TestCase):
    def test_parse_rejects_shell_metachars(self):
        import tools.scc.runtime.run_child_task as rct

        with self.assertRaises(Exception):
            rct._parse_cmdline("echo hi & dir")

        with self.assertRaises(Exception):
            rct._parse_cmdline("echo hi | more")

        with self.assertRaises(Exception):
            rct._parse_cmdline("echo hi > out.txt")

    def test_parse_accepts_simple_argv(self):
        import tools.scc.runtime.run_child_task as rct

        argv = rct._parse_cmdline('python -c "print(123)"')
        self.assertTrue(isinstance(argv, list) and len(argv) >= 3)


if __name__ == "__main__":
    unittest.main()

