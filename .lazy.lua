-- Project-local LazyVim delta for chatgpt-toolbox.
--
-- Ownership boundaries:
--   * uv owns the Python environment and project dependencies.
--   * Neovim discovers executables; it does not install or synchronize them.
--   * .neoconf.json owns project-local LSP settings only.
--   * .lazy.lua owns plugin topology and executable adapters.
--   * CUE, Go, and Lua toolchains are repository build artifacts, not
--     project language-runtime dependencies.
--   * Mason remains disabled by the user-level Neovim configuration.

local source = debug.getinfo(1, "S").source
local file = source:sub(1, 1) == "@" and source:sub(2) or source
local root = vim.fs.dirname(vim.uv.fs_realpath(file) or file)

local function project_path(...)
  return table.concat({ root, ... }, "/")
end

local function project_executable(name)
  local candidate = project_path(".venv", "bin", name)
  if vim.uv.fs_stat(candidate) then
    return candidate
  end
  return name
end

local function project_python()
  -- Deliberately do not fall back to a host interpreter. Tests and debugging
  -- must run through the environment materialized by `uv sync`.
  return project_path(".venv", "bin", "python")
end

-- ty owns Python language intelligence and type diagnostics.
-- Ruff is kept out of the LSP graph: Conform owns formatting and nvim-lint
-- owns external lint projection.
vim.g.lazyvim_python_lsp = "ty"
vim.g.lazyvim_python_ruff = "ruff"

return {
  { import = "lazyvim.plugins.extras.lang.python" },

  -- This repository has one deterministic uv environment at .venv.
  -- Do not introduce an alternate interactive environment selector.
  {
    "linux-cultist/venv-selector.nvim",
    enabled = false,
  },

  {
    "neovim/nvim-lspconfig",
    dependencies = {
      {
        "folke/neoconf.nvim",
        opts = {
          local_settings = ".neoconf.json",
          import = {
            vscode = false,
            coc = false,
            nlsp = false,
          },
        },
      },
    },
    opts = function(_, opts)
      opts.servers = opts.servers or {}

      for _, server in ipairs({ "pyright", "basedpyright", "ruff", "ruff_lsp" }) do
        opts.servers[server] = vim.tbl_deep_extend("force", opts.servers[server] or {}, {
          enabled = false,
          mason = false,
        })
      end

      opts.servers.ty = vim.tbl_deep_extend("force", opts.servers.ty or {}, {
        enabled = true,
        mason = false,
        cmd = { project_executable("ty"), "server" },
        filetypes = { "python" },
        root_markers = { "pyproject.toml", "uv.lock", ".git" },
      })
    end,
  },

  {
    "stevearc/conform.nvim",
    opts = function(_, opts)
      opts.formatters_by_ft = opts.formatters_by_ft or {}
      opts.formatters = opts.formatters or {}

      opts.formatters_by_ft.python = { "ruff_format" }
      opts.formatters.ruff_format = vim.tbl_deep_extend("force", opts.formatters.ruff_format or {}, {
        command = project_executable("ruff"),
      })
    end,
  },

  {
    "mfussenegger/nvim-lint",
    opts = function(_, opts)
      opts.linters_by_ft = opts.linters_by_ft or {}
      opts.linters = opts.linters or {}

      opts.linters_by_ft.python = { "ruff" }
      opts.linters.ruff = vim.tbl_deep_extend("force", opts.linters.ruff or {}, {
        cmd = project_executable("ruff"),
      })
    end,
  },

  {
    "nvim-neotest/neotest",
    optional = true,
    opts = function(_, opts)
      opts.adapters = opts.adapters or {}
      opts.adapters["neotest-python"] = vim.tbl_deep_extend(
        "force",
        opts.adapters["neotest-python"] or {},
        {
          runner = "pytest",
          python = project_python(),
        }
      )
    end,
  },

  {
    "mfussenegger/nvim-dap-python",
    optional = true,
    config = function()
      require("dap-python").setup(project_python())
    end,
  },
}
