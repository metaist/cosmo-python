"""
Import hook for .cosmoext extension modules.

This module provides a custom finder and loader that integrates with Python's
import system to automatically load .cosmoext files.

Usage:
    import _cosmoext_importer  # Installs the import hook
    import myextension  # Will find myextension.cosmoext in sys.path

The hook searches for .cosmoext files in sys.path. When found, it uses the
_cosmoext built-in module to load the extension.

For Cython extensions with relative imports, ensure the parent package is
properly set up before importing the extension.
"""

import sys
import os
from importlib.abc import MetaPathFinder, Loader
from importlib.machinery import ModuleSpec
from importlib.util import spec_from_loader


class CosmoExtLoader(Loader):
    """Loader for .cosmoext extension modules."""
    
    def __init__(self, path: str, fullname: str):
        self.path = path
        self.fullname = fullname
    
    def create_module(self, spec):
        """Create the module by loading the .cosmoext file."""
        import _cosmoext
        
        # Load the extension - this returns the module object
        module = _cosmoext.load(self.path)
        
        if module is None:
            raise ImportError(f"Failed to load {self.path}")
        
        # Set module attributes for proper import behavior
        module.__name__ = self.fullname
        module.__loader__ = self
        module.__file__ = self.path
        module.__spec__ = spec
        
        # Set __package__ for relative imports
        if '.' in self.fullname:
            module.__package__ = self.fullname.rsplit('.', 1)[0]
        else:
            module.__package__ = self.fullname
        
        return module
    
    def exec_module(self, module):
        """Execute the module (no-op for C extensions)."""
        # C extensions are already initialized in create_module
        pass


class CosmoExtFinder(MetaPathFinder):
    """Finder for .cosmoext extension modules."""
    
    def find_spec(self, fullname, path, target=None):
        """Find a .cosmoext file for the given module name."""
        # Convert module name to filename
        # e.g., "mypackage.myext" -> "mypackage/myext.cosmoext"
        parts = fullname.split('.')
        
        # Search paths - use path if provided (for submodules), else sys.path
        search_paths = path if path else sys.path
        
        for search_path in search_paths:
            if not isinstance(search_path, str):
                continue
            if not os.path.isdir(search_path):
                continue
            
            # Try direct module name
            cosmoext_path = os.path.join(search_path, f"{parts[-1]}.cosmoext")
            if os.path.isfile(cosmoext_path):
                loader = CosmoExtLoader(cosmoext_path, fullname)
                return spec_from_loader(fullname, loader, origin=cosmoext_path)
            
            # For submodules, also try the full path
            if len(parts) > 1:
                rel_path = os.path.join(*parts[:-1], f"{parts[-1]}.cosmoext")
                cosmoext_path = os.path.join(search_path, rel_path)
                if os.path.isfile(cosmoext_path):
                    loader = CosmoExtLoader(cosmoext_path, fullname)
                    return spec_from_loader(fullname, loader, origin=cosmoext_path)
        
        # Not found
        return None


# Global finder instance
_finder = None


def install():
    """Install the cosmoext import hook."""
    global _finder
    if _finder is None:
        _finder = CosmoExtFinder()
        # Insert at the beginning to check before other finders
        sys.meta_path.insert(0, _finder)
        return True
    return False


def uninstall():
    """Remove the cosmoext import hook."""
    global _finder
    if _finder is not None and _finder in sys.meta_path:
        sys.meta_path.remove(_finder)
        _finder = None
        return True
    return False


def is_installed():
    """Check if the import hook is installed."""
    return _finder is not None and _finder in sys.meta_path


# Auto-install when this module is imported
install()
