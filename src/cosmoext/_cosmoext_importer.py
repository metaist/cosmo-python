"""
Import hook for .cosmoext extension modules.

This module provides a custom finder and loader that integrates with Python's
import system to automatically load .cosmoext files.

Usage:
    import _cosmoext_importer  # Installs the import hook
    import myextension  # Will find myextension.cosmoext in sys.path

The hook searches for .cosmoext files in sys.path. When found, it uses the
_cosmoext.create_dynamic(spec) function which properly sets __package__
before calling the extension's init function, enabling relative imports
in Cython extensions.
"""

import sys
import os
from importlib.abc import MetaPathFinder, Loader
from importlib.machinery import ModuleSpec
from importlib.util import spec_from_loader


class CosmoExtLoader(Loader):
    """Loader for .cosmoext extension modules.
    
    This loader uses _cosmoext.create_dynamic(spec) which sets the package
    context before calling PyInit_*, enabling relative imports during init.
    """
    
    def __init__(self, path: str, fullname: str):
        self.path = path
        self.fullname = fullname
    
    def create_module(self, spec):
        """Create the module by loading the .cosmoext file.
        
        Uses _cosmoext.create_dynamic(spec) which:
        1. Sets package context via _PyImport_SwapPackageContext
        2. Calls the extension's PyInit_* function  
        3. Sets __name__, __file__, __package__, __spec__ from spec
        """
        import _cosmoext
        
        # Use create_dynamic which properly handles package context
        module = _cosmoext.create_dynamic(spec)
        
        if module is None:
            raise ImportError(f"Failed to load {self.path}")
        
        # Set loader (create_dynamic sets it to None)
        module.__loader__ = self
        
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
            
            # Try direct module name (e.g., crc32c.cosmoext)
            cosmoext_path = os.path.join(search_path, f"{parts[-1]}.cosmoext")
            if os.path.isfile(cosmoext_path):
                loader = CosmoExtLoader(cosmoext_path, fullname)
                return spec_from_loader(fullname, loader, origin=cosmoext_path)
            
            # For submodules, also try the full path
            # e.g., mypackage/myext.cosmoext for mypackage.myext
            if len(parts) > 1:
                rel_path = os.path.join(*parts[:-1], f"{parts[-1]}.cosmoext")
                cosmoext_path = os.path.join(search_path, rel_path)
                if os.path.isfile(cosmoext_path):
                    loader = CosmoExtLoader(cosmoext_path, fullname)
                    return spec_from_loader(fullname, loader, origin=cosmoext_path)
        
        # Not found - let other finders try
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
