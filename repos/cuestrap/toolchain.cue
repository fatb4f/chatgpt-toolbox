package toolchain

// bundle is the authority for the first Linux AMD64 tool bundles.
bundle: {
	schema: "cuestrap.toolchain-lock/v2"
	target: {
		os:   "linux"
		arch: "amd64"
		abi: {
			libc:       "glibc"
			minVersion: "2.17"
		}
	}
	hostRequirements: commands: [
		"cc",
		"make",
		"sha256sum",
		"tar",
		"zstd",
	]
	archive: {
		compression: {
			algorithm: "zstd"
			level:     10
			threads:   2
		}
	}
	pythonEnvironment: {
		lockPath: "uv.lock"
		sha256:   "e54d85a6e3c1b7c9c8801eeeb1b1690c6cd9ca714ae05b8f5c51cce56469dac3"
		additionalWheels: {
			setuptools: {
				version: "80.9.0"
				source:  "https://files.pythonhosted.org/packages/a3/dc/17031897dae0efacfea57dfd3a82fdd2a2aeb58e0ff71b77b87e44edc772/setuptools-80.9.0-py3-none-any.whl"
				sha256:  "062d34222ad13e0cc312a4c02d73f059e86a4acbfbdea8f8f76b28c99f306922"
			}
			wheel: {
				version: "0.45.1"
				source:  "https://files.pythonhosted.org/packages/0b/2c/87f3254fd8ffd29e4c02732eee68a83a1d3c346ae39bc6822dcbcb697f2b/wheel-0.45.1-py3-none-any.whl"
				sha256:  "708e7481cc80179af0e556bbf0cc00b8444c7321e2700b8d8580231d13017248"
			}
		}
	}
	tools: {
		python: {
			version:  "3.14.3"
			revision: "python-build-standalone/20260203"
			source:   "https://github.com/astral-sh/python-build-standalone/releases/download/20260203/cpython-3.14.3%2B20260203-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
			sha256:   "d2a2c12cc62b9de249ed9f7c66c6382c76788b464297aaed165853e18643f9e7"
		}
		go: {
			version:  "1.26.5"
			revision: "c19862e5f8415b4f24b189d065ed739517c548ba"
			source:   "https://go.dev/dl/go1.26.5.linux-amd64.tar.gz"
			sha256:   "5c2c3b16caefa1d968a94c1daca04a7ca301a496d9b086e17ad77bb81393f053"
		}
		cue: {
			version:      "0.18.0"
			revision:     "806821e40fae070318600a264d311517e596353b"
			moduleTarget: "v0.18.0"
			source:       "https://github.com/cue-lang/cue.git"
		}
		gopls: {
			version:  "0.23.0"
			revision: "014f87ff5c01915bc90f4f11a6bb8aea3e0edbd7"
			source:   "https://github.com/golang/tools.git"
		}
		goimports: {
			version:  "0.39.0+cuestrap.014f87f"
			revision: "014f87ff5c01915bc90f4f11a6bb8aea3e0edbd7"
			source:   "https://github.com/golang/tools.git"
		}
		gopy: {
			version:  "0.4.10+cuestrap.72557f6"
			revision: "72557f647208599c726c14dc9721a6c850d2e6d9"
			source:   "https://github.com/go-python/gopy.git"
			patch: {
				path:   "tools/bundles/gopy-python-config.patch"
				sha256: "bfd9d15f0172428f98f6e1b9c42067babc7856d7566c0294d6f155a2ff740696"
			}
			offlineModule: {
				version: "v0.4.11-0.20260602125840-72557f647208"
				time:    "2026-06-02T12:58:40Z"
				artifacts: {
					info: {
						source: "https://proxy.golang.org/github.com/go-python/gopy/@v/v0.4.11-0.20260602125840-72557f647208.info"
						sha256: "f985b3308d3e0bb28420dec25857e58c9416c51ef2e10c09e167bb44ad16f9f2"
					}
					mod: {
						source: "https://proxy.golang.org/github.com/go-python/gopy/@v/v0.4.11-0.20260602125840-72557f647208.mod"
						sha256: "36db3f398ff683a10e87d31e473ebbc0c635281369391a8ea36386e24cfa3e56"
					}
					zip: {
						source: "https://proxy.golang.org/github.com/go-python/gopy/@v/v0.4.11-0.20260602125840-72557f647208.zip"
						sha256: "11cce452d9f34d02388e0f2f700eb8683485d31d1fc7584ea144b821dab5cd30"
					}
				}
			}
		}
	}
}
