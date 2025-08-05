import gdb
import os
from .dwarf.tree import DWARFTreeModel, cu_sort_key
from .dwarf.formats import read_dwarf

class initDwarfAnalysisCommand(gdb.Command):
    """Initialize Dwarf analysis.
    
    Usage: init-dwarf-analysis <path_to_executable>
    
    This command loads the DWARF information from the specified executable
    and creates a tree model for analysis.
    
    Example:
        (gdb) init-dwarf-analysis /path/to/your/executable
        (gdb) python tree = gdb.dwarf_tree  # Access the tree model
        (gdb) python info = gdb.dwarf_info  # Access the DWARF info
    """

    def __init__(self):
        super().__init__("init-dwarf-analysis", gdb.COMMAND_USER)
        self.dwarf_tree = None

    def invoke(self, arg, from_tty):
        if not arg.strip():
            print("Error: Please provide the path to the executable with DWARF information")
            print("Usage: init-dwarf-analysis <path_to_executable>")
            return
        
        executable_path = arg.strip()
        
        if not os.path.exists(executable_path):
            print(f"Error: File '{executable_path}' does not exist")
            return
        
        if not os.path.isfile(executable_path):
            print(f"Error: '{executable_path}' is not a file")
            return
        
        try:
            print(f"Loading DWARF information from: {executable_path}")
            
            # Read DWARF information from the executable
            # Using a simple resolver that returns the first arch for multi-arch binaries
            def simple_resolver(arches, title=None, message=None):
                if isinstance(arches, list) and len(arches) > 0:
                    return 0  # Return first architecture
                return None
            
            try:
                dwarf_info = read_dwarf(executable_path, simple_resolver)
            except ImportError as e:
                if "PyQt" in str(e) or "Qt" in str(e):
                    print("Error: Qt dependencies detected but not available in this environment")
                    print("This tool is designed to work without Qt dependencies")
                    return
                else:
                    raise
            
            if dwarf_info is None:
                print("Error: No DWARF information found in the file")
                return
            
            if dwarf_info is False:
                print("Error: Failed to read DWARF information (operation cancelled)")
                return
            
            # Initialize the DWARF tree model
            # Set up similar to the original dwex application
            def decorate_cu(cu, i):
                cu._i = i
                cu._lineprogram = None
                cu._exprparser = None
                return cu
            
            # Cache compilation units
            dwarf_info._unsorted_CUs = [decorate_cu(cu, i) for (i, cu) in enumerate(dwarf_info.iter_CUs())]
            dwarf_info._CU_offsets = [cu.cu_offset for cu in dwarf_info._unsorted_CUs]
            dwarf_info._CUs = list(dwarf_info._unsorted_CUs)
            
            # Sort compilation units by filename
            dwarf_info._CUs.sort(key=cu_sort_key)
            for (i, cu) in enumerate(dwarf_info._CUs):
                cu._i = i
                
            dwarf_info._locparser = None
            
            # Create the tree model
            # Parameters: dwarf_info, prefix, sortcus, sortdies
            self.dwarf_tree = DWARFTreeModel(dwarf_info, True, True, True)
            
            print(f"Successfully initialized DWARF analysis for: {executable_path}")
            print(f"Found {len(dwarf_info._CUs)} compilation units")
            print("You can now access the tree with: python tree = gdb.dwarf_tree")
            print("Or access DWARF info with: python info = gdb.dwarf_info")
            
            # Store references for later use
            gdb.dwarf_info = dwarf_info
            gdb.dwarf_tree = self.dwarf_tree
            
        except Exception as e:
            print(f"Error initializing DWARF analysis: {str(e)}")
            import traceback
            traceback.print_exc()

def get_dwarf_tree():
    """Get the initialized DWARF tree model.
    
    Returns:
        DWARFTreeModel: The initialized DWARF tree model, or None if not initialized
    """
    return getattr(gdb, 'dwarf_tree', None)

def get_dwarf_info():
    """Get the initialized DWARF information.
    
    Returns:
        DWARFInfo: The initialized DWARF info object, or None if not initialized
    """
    return getattr(gdb, 'dwarf_info', None)

initDwarfAnalysisCommand()

