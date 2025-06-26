import pytest
from ufo2ft.featureWriters.markFeatureWriter import MarkFeatureWriter


def test_nukta_variants():
    """Test that anchors named nukta_1, nukta_2 etc are correctly classified as below marks."""
    writer = MarkFeatureWriter()
    
    # Mock anchor objects for testing
    nukta1 = type('Anchor', (), {'name': 'nukta_1'})
    nukta2 = type('Anchor', (), {'name': 'nukta_2'})
    
    # These should be classified as below marks
    assert not writer._isAboveMark(nukta1)
    assert not writer._isAboveMark(nukta2)
    
    # Regular nukta should still work
    nukta = type('Anchor', (), {'name': 'nukta'})
    assert not writer._isAboveMark(nukta)
    
    # Other below mark anchors should still work
    bottom = type('Anchor', (), {'name': 'bottom'})
    assert not writer._isAboveMark(bottom)
    
    # Above mark anchors should still work
    top = type('Anchor', (), {'name': 'top'})
    assert writer._isAboveMark(top)
