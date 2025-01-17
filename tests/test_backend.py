"""Tests for backend functions."""

import numpy as np
import pytest

from desc.backend import put, sign


@pytest.mark.unit
def test_put():
    """Test put function as replacement for fancy array indexing."""
    a = np.array([0, 0, 0])
    b = np.array([1, 2, 3])

    a = put(a, np.array([0, 1, 2]), np.array([1, 2, 3]))

    np.testing.assert_array_almost_equal(a, b)


@pytest.mark.unit
def test_sign():
    """Test modified sign function to return +1 for x=0."""
    assert sign(4) == 1
    assert sign(0) == 1
    assert sign(-10.3) == -1
