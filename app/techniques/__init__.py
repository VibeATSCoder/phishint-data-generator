"""
Importing each group package triggers their __init__.py,
which imports all technique modules, triggering BaseTechnique.__init_subclass__
auto-registration in TechniqueRegistry.
"""
import app.techniques.group1_url  # noqa: F401
import app.techniques.group2_visual  # noqa: F401
import app.techniques.group3_html  # noqa: F401
import app.techniques.group4_antibot  # noqa: F401
import app.techniques.group5_delivery  # noqa: F401
import app.techniques.group6_mfa  # noqa: F401
import app.techniques.group7_advanced  # noqa: F401
