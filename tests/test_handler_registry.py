"""
Tests for HandlerRegistry — signature-aware handler selection.

Verifies that HandlerRegistry.handlers_for_params returns the correct
handler type for each annotated parameter, with proper fallback for
unannotated parameters.
"""

import unittest
from type_handlers.registry import HandlerRegistry
from type_handlers.float_handler import FloatHandler
from type_handlers.integer_handler import IntegerHandler
from type_handlers.string_handler import StringHandler
from type_handlers.bool_handler import BoolHandler


class TestHandlerRegistry(unittest.TestCase):

    # ------------------------------------------------------------------
    # 1. float annotation → FloatHandler
    # ------------------------------------------------------------------
    def test_float_annotation_returns_float_handler(self):
        """A parameter annotated as float must yield a FloatHandler."""
        handlers = HandlerRegistry.handlers_for_params(('x',), {'x': float})
        self.assertEqual(len(handlers), 1)
        self.assertIsInstance(handlers[0], FloatHandler)

    # ------------------------------------------------------------------
    # 2. str annotation → StringHandler
    # ------------------------------------------------------------------
    def test_str_annotation_returns_string_handler(self):
        """A parameter annotated as str must yield a StringHandler."""
        handlers = HandlerRegistry.handlers_for_params(('s',), {'s': str})
        self.assertEqual(len(handlers), 1)
        self.assertIsInstance(handlers[0], StringHandler)

    # ------------------------------------------------------------------
    # 3. bool annotation → BoolHandler
    # ------------------------------------------------------------------
    def test_bool_annotation_returns_bool_handler(self):
        """A parameter annotated as bool must yield a BoolHandler."""
        handlers = HandlerRegistry.handlers_for_params(('b',), {'b': bool})
        self.assertEqual(len(handlers), 1)
        self.assertIsInstance(handlers[0], BoolHandler)

    # ------------------------------------------------------------------
    # 4. No annotation → FloatHandler fallback
    # ------------------------------------------------------------------
    def test_no_annotation_falls_back_to_float_handler(self):
        """A parameter with no annotation must fall back to FloatHandler."""
        handlers = HandlerRegistry.handlers_for_params(('x',), {})
        self.assertEqual(len(handlers), 1)
        self.assertIsInstance(handlers[0], FloatHandler)

    # ------------------------------------------------------------------
    # 5. Mixed annotations → correct handler per parameter
    # ------------------------------------------------------------------
    def test_mixed_annotations_return_correct_handler_types(self):
        """Two params with different annotations must each get the right handler."""
        handlers = HandlerRegistry.handlers_for_params(
            ('a', 'b'),
            {'a': float, 'b': str}
        )
        self.assertEqual(len(handlers), 2)
        self.assertIsInstance(handlers[0], FloatHandler)
        self.assertIsInstance(handlers[1], StringHandler)

    # ------------------------------------------------------------------
    # 6. int annotation → IntegerHandler
    # ------------------------------------------------------------------
    def test_int_annotation_returns_integer_handler(self):
        """A parameter annotated as int must yield an IntegerHandler."""
        handlers = HandlerRegistry.handlers_for_params(('n',), {'n': int})
        self.assertEqual(len(handlers), 1)
        self.assertIsInstance(handlers[0], IntegerHandler)

    # ------------------------------------------------------------------
    # 7. Multiple params, one missing annotation → fallback for that param
    # ------------------------------------------------------------------
    def test_partial_annotations_fallback_for_missing(self):
        """A param without annotation in a multi-param list must fall back to FloatHandler."""
        handlers = HandlerRegistry.handlers_for_params(
            ('a', 'b'),
            {'a': str}  # 'b' is not annotated
        )
        self.assertEqual(len(handlers), 2)
        self.assertIsInstance(handlers[0], StringHandler)
        self.assertIsInstance(handlers[1], FloatHandler)

    # ------------------------------------------------------------------
    # 8. Empty parameters → empty handler list
    # ------------------------------------------------------------------
    def test_empty_parameters_returns_empty_list(self):
        """No parameters must return an empty handler list."""
        handlers = HandlerRegistry.handlers_for_params((), {})
        self.assertEqual(handlers, [])


if __name__ == "__main__":
    unittest.main()
