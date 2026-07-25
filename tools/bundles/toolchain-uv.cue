package toolchain

// Bundle-owned extension for the native UV executable. The base repository
// lock may later define the same entry; CUE unification then requires an exact
// match rather than permitting the builder to silently select another release.
bundle: tools: uv: {
	version:  "0.11.32"
	revision: "2cf57f594cacc1643947dfc89ae49fce5e66e29f"
	target:   "x86_64-unknown-linux-gnu"
	source:   "https://github.com/astral-sh/uv/releases/download/0.11.32/uv-x86_64-unknown-linux-gnu.tar.gz"
	sha256:   "0a48426481cac4927441f6875f7c7b07cfcc72cb96803d6e0103c55b8e3040cf"
}
