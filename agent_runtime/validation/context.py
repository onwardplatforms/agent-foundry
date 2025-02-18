# """Validation context and error handling."""

# from dataclasses import dataclass, field
# from typing import List, Any
# from contextlib import contextmanager


# @dataclass
# class ValidationError:
#     """A validation error with path information."""

#     path: List[str]
#     message: str

#     def __str__(self) -> str:
#         path_str = " -> ".join(self.path) if self.path else "root"
#         return f"{path_str}: {self.message}"


# @dataclass
# class ValidationContext:
#     """Context for validation operations, tracking errors and current path."""

#     errors: List[ValidationError] = field(default_factory=list)
#     _path: List[str] = field(default_factory=list)

#     def add_error(self, message: str) -> None:
#         """Add an error at the current path."""
#         self.errors.append(ValidationError(self._path.copy(), message))

#     @contextmanager
#     def path(self, *elements: str):
#         """Context manager to track the current validation path."""
#         self._path.extend(elements)
#         try:
#             yield
#         finally:
#             for _ in elements:
#                 self._path.pop()

#     @property
#     def has_errors(self) -> bool:
#         """Whether any errors have been accumulated."""
#         return len(self.errors) > 0

#     def format_errors(self) -> str:
#         """Format all errors into a readable string."""
#         return "\n".join(str(error) for error in self.errors)
