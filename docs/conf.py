# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import os
import sys
PROJECT_ROOT = os.path.abspath(os.path.join('..', 'src'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

project = 'hazrakah'
author = 'Shaun Wilson'
copyright = f'2026 {author}'
from hazrakah import __version__
release = f'{__version__}'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx_design',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',       # nice summary tables
    'sphinx.ext.intersphinx',
    'sphinx_autodoc_typehints'     # type-hint rendering
]

autosummary_generate = True        # generate stub pages automatically

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_title = "hazrakah&nbsp;<span style='font-size: small'>(הזרקה)</span><br><span style='font-size: x-small'>..a tiny but powerful DI library for Python.</span>"
html_static_path = ['_static']
html_theme_options = {
    'analytics_anonymize_ip': False,
    'logo_only': False,
    'prev_next_buttons_location': 'bottom',
    'style_external_links': False,
    'vcs_pageview_mode': '',
    'style_nav_header_background': 'steelblue',
    # Toc options
    'collapse_navigation': True,
    'sticky_navigation': True,
    'navigation_depth': 3,
    'includehidden': True,
    'titles_only': True
}


#
autodoc_member_order = 'bysource'
autoclass_content = 'both'
html_show_sourcelink = False
autodoc_inherit_docstrings = True
set_type_checking_flag = True
add_module_names = False

pygments_style = 'friendly'
pygments_dark_style = 'monokai'

html_permalinks_icon = '<span>#</span>'

toc_object_entries_show_parents = 'hide'
add_presentation_hints = True
