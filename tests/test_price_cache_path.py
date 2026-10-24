"""The bean-price cache lives under the XDG cache home, so it outlives the temp dir."""

from pathlib import Path

from beancount_cli.commands.price import price_cache_path


def test_xdg_cache_home_is_used(tmp_path: Path) -> None:
    assert price_cache_path({"XDG_CACHE_HOME": str(tmp_path)}) == tmp_path / "bean-price"


def test_relative_xdg_cache_home_falls_back_to_home_cache() -> None:
    assert price_cache_path({"XDG_CACHE_HOME": "cache"}) == Path.home() / ".cache" / "bean-price"


def test_default_is_home_cache() -> None:
    assert price_cache_path({}) == Path.home() / ".cache" / "bean-price"
