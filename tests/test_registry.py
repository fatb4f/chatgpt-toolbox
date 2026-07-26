from toolbox.registry import TOOLS, get_repository, topological_tools


def test_dotfiles_registry_is_closed_and_complete() -> None:
    repository = get_repository("dotfiles")
    assert tuple(repository.tools) == (
        "python",
        "go",
        "cue",
        "gopls",
        "goimports",
        "uv",
        "lua",
        "luals",
        "go-git",
        "context-git-hydrator",
    )
    assert set(repository.tools) <= set(TOOLS)


def test_dotfiles_build_graph_orders_dependencies() -> None:
    order = [tool.name for tool in topological_tools(get_repository("dotfiles"))]
    positions = {name: index for index, name in enumerate(order)}
    assert positions["go"] < positions["gopls"]
    assert positions["go"] < positions["goimports"]
    assert positions["go"] < positions["cue"]
    assert positions["go"] < positions["context-git-hydrator"]
    assert positions["go-git"] < positions["context-git-hydrator"]
    assert positions["lua"] < positions["luals"]
