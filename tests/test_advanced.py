from beancount_cli.models import AccountModel
from beancount_cli.services import AccountService, LedgerService, MapService


def test_complex_include_structure(tmp_path):
    """
    Test a structure like:
    root.beancount
      -> sub/middle.beancount
        -> sub/leaf/*.beancount (glob)
    """
    root_file = tmp_path / "root.beancount"
    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    leaf_dir = sub_dir / "leaf"
    leaf_dir.mkdir()

    middle_file = sub_dir / "middle.beancount"
    leaf1 = leaf_dir / "one.beancount"
    leaf2 = leaf_dir / "two.beancount"

    root_file.write_text('include "sub/middle.beancount"')
    middle_file.write_text('include "leaf/*.beancount"')
    leaf1.write_text("2024-01-01 open Assets:One USD")
    leaf2.write_text("2024-01-01 open Assets:Two USD")

    # 1. Test MapService
    map_service = MapService(root_file)
    tree = map_service.get_include_tree()

    assert str(middle_file) in tree
    sub_tree = tree[str(middle_file)]
    assert str(leaf1) in sub_tree
    assert str(leaf2) in sub_tree

    # 2. Test LedgerService loading
    ledger = LedgerService(root_file)
    ledger.load()
    accounts = ledger.get_accounts()
    assert "Assets:One" in accounts
    assert "Assets:Two" in accounts


def test_subfile_config_resolution(tmp_path):
    """
    Test that cli-config in a sub-included file is correctly used.
    """
    root_file = tmp_path / "root.beancount"
    inc_dir = tmp_path / "includes"
    inc_dir.mkdir()
    inc_file = inc_dir / "config.beancount"

    # Config file defines a target relative to ITSELF or ROOT?
    # services.py resolves relative to the ledger_file passed to Service.
    # Usually the root ledger is passed.

    root_file.write_text('include "includes/config.beancount"')
    inc_file.write_text(
        '2024-01-01 custom "cli-config" "new_account_file" "local_accounts.beancount"'
    )

    # Passing ROOT file to service
    service = AccountService(root_file)

    # The current implementation resolves relative to whatever file was passed to Service.
    # If we pass root_file, it looks for "local_accounts.beancount" in tmp_path/

    # Let's verify this behavior
    model = AccountModel(name="Assets:Test", currencies=["USD"])
    service.create_account(model)

    target = tmp_path / "local_accounts.beancount"
    assert target.exists()
    assert "Assets:Test" in target.read_text()


def test_deep_nesting_performance(tmp_path):
    """
    Test deep nesting level.
    """
    curr = tmp_path / "0.beancount"
    curr.write_text("2024-01-01 open Assets:Root USD")

    for i in range(1, 10):
        next_file = tmp_path / f"{i}.beancount"
        next_file.write_text(f'include "{i - 1}.beancount"')
        curr = next_file

    ledger = LedgerService(curr)
    ledger.load()
    assert "Assets:Root" in ledger.get_accounts()

    map_service = MapService(curr)
    tree = map_service.get_include_tree()

    # verify we can reach level 0
    def find_level_0(t):
        if str(tmp_path / "0.beancount") in t:
            return True
        for st in t.values():
            if find_level_0(st):
                return True
        return False

    assert find_level_0(tree)
