local source = debug.getinfo(1, "S").source
local file = source:sub(1, 1) == "@" and source:sub(2) or source
local root = vim.fs.dirname(vim.uv.fs_realpath(file) or file)

local function project_python()
	return root .. "/.venv/bin/python"
end

vim.g.lazyvim_python_lsp = "ty"
vim.g.lazyvim_python_ruff = "ruff"

return {
	{ import = "lazyvim.plugins.extras.lang.python" },

	{ "mason-org/mason.nvim", enabled = false },
	{ "mason-org/mason-lspconfig.nvim", enabled = false },
	{ "jay-babu/mason-nvim-dap.nvim", enabled = false },
	{ "linux-cultist/venv-selector.nvim", enabled = false },

	{
		"neovim/nvim-lspconfig",
		init = function()
			for _, executable in ipairs({ "ty", "ruff" }) do
				if vim.fn.executable(executable) ~= 1 then
					vim.schedule(function()
						vim.notify(
							executable .. " is required but unavailable on PATH",
							vim.log.levels.ERROR,
							{ title = "chatgpt-toolbox" }
						)
					end)
				end
			end
		end,
		opts = function(_, opts)
			opts.servers = opts.servers or {}

			for _, server in ipairs({
				"pyright",
				"basedpyright",
				"ruff",
				"ruff_lsp",
			}) do
				opts.servers[server] = vim.tbl_deep_extend("force", opts.servers[server] or {}, {
					enabled = false,
					mason = false,
				})
			end

			opts.servers.ty = vim.tbl_deep_extend("force", opts.servers.ty or {}, {
				enabled = true,
				mason = false,
				settings = {
					ty = {
						diagnosticMode = "openFilesOnly",
					},
				},
			})
		end,
	},

	{
		"stevearc/conform.nvim",
		opts = function(_, opts)
			opts.formatters_by_ft = opts.formatters_by_ft or {}
			opts.formatters_by_ft.python = { "ruff_format" }
		end,
	},

	{
		"mfussenegger/nvim-lint",
		opts = function(_, opts)
			opts.linters_by_ft = opts.linters_by_ft or {}
			opts.linters_by_ft.python = { "ruff" }
		end,
	},

	{
		"nvim-neotest/neotest",
		optional = true,
		opts = function(_, opts)
			opts.adapters = opts.adapters or {}
			opts.adapters["neotest-python"] = vim.tbl_deep_extend("force", opts.adapters["neotest-python"] or {}, {
				runner = "pytest",
				python = project_python(),
			})
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
