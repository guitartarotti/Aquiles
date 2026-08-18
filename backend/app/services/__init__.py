"""Service package.

Submodules are imported directly by the APIs and dedicated workers. Keeping this
package initializer light prevents side-effect imports from loading pandas,
numpy, and graph/LLM services in small standalone processes.
"""

__all__: list[str] = []
