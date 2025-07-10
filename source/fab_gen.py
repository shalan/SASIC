#!/usr/bin/env python3
"""
Sky130 Structured ASIC Fabric Generator

A complete tool for generating Sky130-based structured ASIC fabrics from JSON specifications.
Supports tile-based composition, edge cells, I/O rings, and multiple output formats.
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.patches import Rectangle
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Data Models using dataclasses
# ============================================================================

@dataclass
class Pin:
    """Pin definition model."""
    direction: str
    capacitance: Optional[float] = None
    layer: Optional[str] = None
    function: Optional[str] = None
    max_capacitance: Optional[float] = None
    max_fanout: Optional[int] = None
    location: Optional[List[float]] = None
    clock: Optional[bool] = None

    def __post_init__(self):
        """Validate pin direction."""
        if self.direction not in ['input', 'output', 'inout']:
            raise ValueError(f"Invalid pin direction: {self.direction}")


@dataclass
class TimingInfo:
    """Timing information model."""
    rise: float
    fall: float


@dataclass
class PowerInfo:
    """Power information model."""
    leakage: float


@dataclass
class Cell:
    """Cell definition model."""
    name: str
    alias: str
    width: int
    height: int
    cell_type: str
    pins: Dict[str, Pin]
    drive_strength: Optional[int] = None
    function: Optional[str] = None
    clock_pin: Optional[str] = None
    spacing_rule: Optional[int] = None
    timing: Optional[Dict[str, Any]] = None  # More flexible timing structure
    power: Optional[PowerInfo] = None


@dataclass
class LayerInfo:
    """Layer information model."""
    direction: str
    pitch: float
    min_width: float
    programmable: bool = False

    def __post_init__(self):
        """Validate layer direction."""
        if self.direction not in ['horizontal', 'vertical']:
            raise ValueError(f"Invalid layer direction: {self.direction}")


@dataclass
class Site:
    """Site definition model."""
    name: str
    width: float
    height: float


@dataclass
class Units:
    """Units definition model."""
    distance: int = 1000
    time: int = 1000
    capacitance: int = 1000
    resistance: int = 1000
    current: int = 1000


@dataclass
class Technology:
    """Technology definition model."""
    technology: str
    version: str
    description: str
    units: Units
    site: Site
    cells: List[Cell]
    layers: Dict[str, LayerInfo]

    def get_cell_by_alias(self, alias: str) -> Optional[Cell]:
        """Get cell by alias."""
        for cell in self.cells:
            if cell.alias == alias:
                return cell
        return None


@dataclass
class CellSpec:
    """Cell specification within a tile row."""
    type: str
    count: int


@dataclass
class TileRow:
    """Tile row definition."""
    row_id: int
    cells: List[CellSpec]


@dataclass
class Tile:
    """Tile definition model."""
    name: str
    description: str
    height: int
    width: int
    site: str
    rows: List[TileRow]

    def __post_init__(self):
        """Basic validation - detailed width validation happens later."""
        if not self.rows:
            return
        
        # Just check that we have the right number of rows
        if len(self.rows) != self.height:
            raise ValueError(f"Tile {self.name}: Expected {self.height} rows, got {len(self.rows)}")
    
    def validate_row_widths(self, technology: Technology) -> None:
        """Validate that all rows have consistent widths using technology data."""
        if not self.rows:
            return
        
        # Calculate first row width in sites
        first_width = 0
        for cell_spec in self.rows[0].cells:
            cell_def = technology.get_cell_by_alias(cell_spec.type)
            if not cell_def:
                raise ValueError(f"Cell type '{cell_spec.type}' not found in technology")
            first_width += cell_spec.count * cell_def.width
        
        # Check that declared tile width matches calculated width
        if first_width != self.width:
            raise ValueError(f"Tile {self.name}: Declared width {self.width} doesn't match calculated width {first_width} sites")
        
        # Check all other rows match the first row width
        for i, row in enumerate(self.rows[1:], 1):
            row_width = 0
            for cell_spec in row.cells:
                cell_def = technology.get_cell_by_alias(cell_spec.type)
                if not cell_def:
                    raise ValueError(f"Cell type '{cell_spec.type}' not found in technology")
                row_width += cell_spec.count * cell_def.width
            
            if row_width != first_width:
                # Provide detailed breakdown for debugging
                first_row_breakdown = []
                for cell_spec in self.rows[0].cells:
                    cell_def = technology.get_cell_by_alias(cell_spec.type)
                    contribution = cell_spec.count * cell_def.width
                    first_row_breakdown.append(f"{cell_spec.count}x{cell_spec.type}({cell_def.width})={contribution}")
                
                current_row_breakdown = []
                for cell_spec in row.cells:
                    cell_def = technology.get_cell_by_alias(cell_spec.type)
                    contribution = cell_spec.count * cell_def.width
                    current_row_breakdown.append(f"{cell_spec.count}x{cell_spec.type}({cell_def.width})={contribution}")
                
                raise ValueError(
                    f"Tile {self.name}: Row {i} width {row_width} sites doesn't match first row width {first_width} sites\n"
                    f"Row 0: {' + '.join(first_row_breakdown)} = {first_width}\n"
                    f"Row {i}: {' + '.join(current_row_breakdown)} = {row_width}"
                )


@dataclass
class TileDefinitions:
    """Tile definitions container."""
    tiles: List[Tile]

    def get_tile_by_name(self, name: str) -> Optional[Tile]:
        """Get tile by name."""
        for tile in self.tiles:
            if tile.name == name:
                return tile
        return None


@dataclass
class Region:
    """Region override definition."""
    name: str
    tile_type: str
    area: Dict[str, int]  # row_start, col_start, width, height


@dataclass
class TileConfiguration:
    """Tile configuration model."""
    default_tile: str
    regions: List[Region] = field(default_factory=list)


@dataclass
class EdgeCellConfig:
    """Edge cell configuration."""
    enable: bool
    cell: str


@dataclass
class EdgeCells:
    """Edge cells configuration."""
    left: Optional[EdgeCellConfig] = None
    right: Optional[EdgeCellConfig] = None
    top: Optional[EdgeCellConfig] = None
    bottom: Optional[EdgeCellConfig] = None


@dataclass
class IOPin:
    """I/O pin definition."""
    name: str
    type: str
    direction: str
    position: Optional[float] = None

    def __post_init__(self):
        """Validate pin direction."""
        if self.direction not in ['input', 'output', 'inout']:
            raise ValueError(f"Invalid pin direction: {self.direction}")


@dataclass
class IOEdge:
    """I/O edge configuration."""
    spacing: str = "auto"
    pins: List[IOPin] = field(default_factory=list)

    def __post_init__(self):
        """Validate edge configuration."""
        if self.spacing not in ['auto', 'manual']:
            raise ValueError(f"Invalid spacing mode: {self.spacing}")
        
        if self.spacing == 'manual':
            for pin in self.pins:
                if pin.position is None:
                    raise ValueError(f"Pin {pin.name} missing position in manual spacing mode")
        elif self.spacing == 'auto':
            for pin in self.pins:
                if pin.position is not None:
                    logger.warning(f"Pin {pin.name} has position field in auto mode - will be ignored")


@dataclass
class PinSize:
    """Pin size configuration."""
    width: float = 1.0
    height: float = 1.0


@dataclass
class IORing:
    """I/O ring configuration."""
    pin_size: PinSize = field(default_factory=PinSize)
    edges: Dict[str, IOEdge] = field(default_factory=dict)


@dataclass
class Margins:
    """Margin configuration."""
    horizontal: float
    vertical: float

    def __post_init__(self):
        """Validate margins are positive."""
        if self.horizontal <= 0 or self.vertical <= 0:
            raise ValueError("Margins must be positive")


@dataclass
class PowerGrid:
    """Power grid configuration."""
    VDD: Optional[Dict[str, Union[str, float]]] = None
    VSS: Optional[Dict[str, Union[str, float]]] = None
    
    def __post_init__(self):
        """Validate power grid configuration."""
        if not self.VDD and not self.VSS:
            raise ValueError("PowerGrid must have at least VDD or VSS defined")
        
        if self.VDD is not None and not isinstance(self.VDD, dict):
            raise ValueError("VDD must be a dictionary")
        if self.VSS is not None and not isinstance(self.VSS, dict):
            raise ValueError("VSS must be a dictionary")


@dataclass
class PowerDistribution:
    """Power distribution configuration."""
    primary_grid: PowerGrid
    secondary_grid: PowerGrid


@dataclass
class ArrayDimensions:
    """Array dimensions model."""
    rows: int
    cols: int

    def __post_init__(self):
        """Validate dimensions are positive."""
        if self.rows <= 0 or self.cols <= 0:
            raise ValueError("Array dimensions must be positive")


@dataclass
class FabricConfiguration:
    """Fabric configuration model."""
    name: str
    array_dimensions: ArrayDimensions
    tile_configuration: TileConfiguration
    description: str = ""  # Make description optional with default
    edge_cells: Optional[EdgeCells] = None
    io_ring: Optional[IORing] = None
    margins: Optional[Margins] = None
    power_distribution: Optional[PowerDistribution] = None

    def __post_init__(self):
        """Validate fabric configuration."""
        if self.io_ring and self.io_ring.edges and not self.margins:
            raise ValueError("Margins must be specified when I/O pins are defined")


# ============================================================================
# Core Data Classes
# ============================================================================

@dataclass
class CellInstance:
    """Represents a placed cell instance."""
    name: str
    cell_type: str
    x: float
    y: float
    width: float
    height: float
    tile_pos: Optional[Tuple[int, int]] = None
    cell_pos: Optional[Tuple[int, int]] = None
    is_edge_cell: bool = False
    edge_direction: Optional[str] = None


@dataclass
class FabricDimensions:
    """Fabric dimensional information."""
    tile_array_rows: int
    tile_array_cols: int
    fabric_rows: int
    fabric_sites: int
    core_width: float
    core_height: float
    die_width: float
    die_height: float
    margin_horizontal: float = 0.0
    margin_vertical: float = 0.0


@dataclass
class PlacedPin:
    """Represents a placed I/O pin."""
    name: str
    direction: str
    pin_type: str
    edge: str
    x: float
    y: float
    width: float
    height: float


@dataclass
class FabricStats:
    """Fabric statistics."""
    cell_counts: Dict[str, int] = field(default_factory=dict)
    edge_cell_counts: Dict[str, int] = field(default_factory=dict)
    combined_cell_counts: Dict[str, int] = field(default_factory=dict)  # Combined fabric + edge cells by type
    total_cells: int = 0
    total_edge_cells: int = 0
    fabric_area_um2: float = 0.0
    die_area_um2: float = 0.0
    total_leakage_power: float = 0.0  # Total leakage power in watts


# ============================================================================
# JSON Parsing Functions
# ============================================================================

def parse_technology(data: Dict[str, Any]) -> Technology:
    """Parse technology JSON data into Technology object."""
    # Filter known fields for Units
    units_fields = {'distance', 'time', 'capacitance', 'resistance', 'current'}
    units_data = {k: v for k, v in data['units'].items() if k in units_fields}
    ignored_units = set(data['units'].keys()) - units_fields
    if ignored_units:
        logger.debug(f"Ignoring unknown units fields: {ignored_units}")
    units = Units(**units_data)
    
    # Filter known fields for Site
    site_fields = {'name', 'width', 'height'}
    site_data = {k: v for k, v in data['site'].items() if k in site_fields}
    ignored_site = set(data['site'].keys()) - site_fields
    if ignored_site:
        logger.debug(f"Ignoring unknown site fields: {ignored_site}")
    site = Site(**site_data)
    
    cells = []
    for cell_data in data['cells']:
        pins = {}
        # Handle empty pins dict for physical cells like TAP
        if 'pins' in cell_data and cell_data['pins']:
            for pin_name, pin_data in cell_data['pins'].items():
                # Filter known fields for Pin - now includes location and clock
                pin_fields = {'direction', 'capacitance', 'layer', 'function', 'max_capacitance', 'max_fanout', 'location', 'clock'}
                filtered_pin_data = {k: v for k, v in pin_data.items() if k in pin_fields}
                ignored_pin = set(pin_data.keys()) - pin_fields
                if ignored_pin:
                    logger.debug(f"Ignoring unknown pin fields for {pin_name}: {ignored_pin}")
                pins[pin_name] = Pin(**filtered_pin_data)
        
        # Handle timing more flexibly - keep as raw dict since sequential cells have different structures
        timing = None
        if 'timing' in cell_data:
            timing = cell_data['timing']  # Keep raw timing data
        
        power = None
        if 'power' in cell_data:
            # Filter known fields for PowerInfo
            power_fields = {'leakage'}
            filtered_power_data = {k: v for k, v in cell_data['power'].items() if k in power_fields}
            ignored_power = set(cell_data['power'].keys()) - power_fields
            if ignored_power:
                logger.debug(f"Ignoring unknown power fields: {ignored_power}")
            power = PowerInfo(**filtered_power_data)
        
        # Filter known fields for Cell - now includes sequential and physical cell fields
        cell_fields = {'name', 'alias', 'width', 'height', 'drive_strength', 'cell_type', 'function', 'clock_pin', 'spacing_rule'}
        filtered_cell_data = {k: v for k, v in cell_data.items() if k in cell_fields}
        ignored_cell = set(cell_data.keys()) - cell_fields - {'pins', 'timing', 'power'}
        if ignored_cell:
            logger.debug(f"Ignoring unknown cell fields for {cell_data.get('name', 'unknown')}: {ignored_cell}")
        
        cell = Cell(
            pins=pins,
            timing=timing,
            power=power,
            **filtered_cell_data
        )
        cells.append(cell)
    
    layers = {}
    for layer_name, layer_data in data['layers'].items():
        # Filter known fields for LayerInfo
        layer_fields = {'direction', 'pitch', 'min_width', 'programmable'}
        filtered_layer_data = {k: v for k, v in layer_data.items() if k in layer_fields}
        ignored_layer = set(layer_data.keys()) - layer_fields
        if ignored_layer:
            logger.debug(f"Ignoring unknown layer fields for {layer_name}: {ignored_layer}")
        layers[layer_name] = LayerInfo(**filtered_layer_data)
    
    # Filter known fields for Technology
    tech_fields = {'technology', 'version', 'description'}
    filtered_tech_data = {k: v for k, v in data.items() if k in tech_fields}
    ignored_tech = set(data.keys()) - tech_fields - {'units', 'site', 'cells', 'layers'}
    if ignored_tech:
        logger.debug(f"Ignoring unknown technology fields: {ignored_tech}")
    
    return Technology(
        units=units,
        site=site,
        cells=cells,
        layers=layers,
        **filtered_tech_data
    )


def parse_tile_definitions(data: Dict[str, Any]) -> TileDefinitions:
    """Parse tile definitions JSON data."""
    tiles = []
    for tile_data in data['tiles']:
        rows = []
        for row_data in tile_data['rows']:
            cells = []
            for cell_data in row_data['cells']:
                # Filter known fields for CellSpec
                cell_spec_fields = {'type', 'count'}
                filtered_cell_data = {k: v for k, v in cell_data.items() if k in cell_spec_fields}
                cells.append(CellSpec(**filtered_cell_data))
            
            # Filter known fields for TileRow
            row_fields = {'row_id'}
            filtered_row_data = {k: v for k, v in row_data.items() if k in row_fields}
            rows.append(TileRow(cells=cells, **filtered_row_data))
        
        # Filter known fields for Tile
        tile_fields = {'name', 'description', 'height', 'width', 'site'}
        filtered_tile_data = {k: v for k, v in tile_data.items() if k in tile_fields}
        
        tile = Tile(rows=rows, **filtered_tile_data)
        tiles.append(tile)
    
    return TileDefinitions(tiles=tiles)


def parse_fabric_configuration(data: Dict[str, Any]) -> FabricConfiguration:
    """Parse fabric configuration JSON data."""
    # Filter known fields for ArrayDimensions
    array_dim_fields = {'rows', 'cols'}
    array_dim_data = {k: v for k, v in data['array_dimensions'].items() if k in array_dim_fields}
    array_dims = ArrayDimensions(**array_dim_data)
    
    regions = []
    if 'regions' in data['tile_configuration']:
        for region_data in data['tile_configuration']['regions']:
            # Filter known fields for Region
            region_fields = {'name', 'tile_type', 'area'}
            filtered_region_data = {k: v for k, v in region_data.items() if k in region_fields}
            regions.append(Region(**filtered_region_data))
    
    # Filter known fields for TileConfiguration
    tile_config_fields = {'default_tile'}
    filtered_tile_config_data = {k: v for k, v in data['tile_configuration'].items() if k in tile_config_fields}
    tile_config = TileConfiguration(regions=regions, **filtered_tile_config_data)
    
    edge_cells = None
    if 'edge_cells' in data:
        edge_data = data['edge_cells']
        edge_cell_fields = {'enable', 'cell'}
        
        edge_cells = EdgeCells(
            left=EdgeCellConfig(**{k: v for k, v in edge_data['left'].items() if k in edge_cell_fields}) if 'left' in edge_data else None,
            right=EdgeCellConfig(**{k: v for k, v in edge_data['right'].items() if k in edge_cell_fields}) if 'right' in edge_data else None,
            top=EdgeCellConfig(**{k: v for k, v in edge_data['top'].items() if k in edge_cell_fields}) if 'top' in edge_data else None,
            bottom=EdgeCellConfig(**{k: v for k, v in edge_data['bottom'].items() if k in edge_cell_fields}) if 'bottom' in edge_data else None
        )
    
    io_ring = None
    if 'io_ring' in data:
        io_data = data['io_ring']
        
        # Filter known fields for PinSize
        pin_size_fields = {'width', 'height'}
        pin_size_data = {k: v for k, v in io_data.get('pin_size', {}).items() if k in pin_size_fields}
        pin_size = PinSize(**pin_size_data)
        
        edges = {}
        for edge_name, edge_data in io_data.get('edges', {}).items():
            pins = []
            for pin_data in edge_data.get('pins', []):
                # Filter known fields for IOPin
                pin_fields = {'name', 'type', 'direction', 'position'}
                filtered_pin_data = {k: v for k, v in pin_data.items() if k in pin_fields}
                pins.append(IOPin(**filtered_pin_data))
            
            # Filter known fields for IOEdge
            edge_fields = {'spacing'}
            filtered_edge_data = {k: v for k, v in edge_data.items() if k in edge_fields}
            edges[edge_name] = IOEdge(pins=pins, **filtered_edge_data)
        
        io_ring = IORing(pin_size=pin_size, edges=edges)
    
    margins = None
    if 'margins' in data:
        # Filter known fields for Margins
        margin_fields = {'horizontal', 'vertical'}
        margin_data = {k: v for k, v in data['margins'].items() if k in margin_fields}
        margins = Margins(**margin_data)
    
    power_dist = None
    if 'power_distribution' in data and data['power_distribution']:
        try:
            logger.debug("Parsing power distribution...")
            power_data = data['power_distribution']
            logger.debug(f"Power data: {power_data}")
            
            # Check if primary_grid and secondary_grid exist
            if 'primary_grid' not in power_data:
                logger.warning("Missing 'primary_grid' in power_distribution - skipping power distribution")
                power_dist = None
            elif 'secondary_grid' not in power_data:
                logger.warning("Missing 'secondary_grid' in power_distribution - skipping power distribution")
                power_dist = None
            else:
                primary_grid_data = power_data['primary_grid']
                secondary_grid_data = power_data['secondary_grid']
                
                logger.debug(f"Primary grid data: {primary_grid_data}")
                logger.debug(f"Secondary grid data: {secondary_grid_data}")
                
                # Validate that at least one power rail exists and create PowerGrid objects
                primary_vdd = primary_grid_data.get('VDD')
                primary_vss = primary_grid_data.get('VSS')
                secondary_vdd = secondary_grid_data.get('VDD')
                secondary_vss = secondary_grid_data.get('VSS')
                
                if not primary_vdd and not primary_vss:
                    logger.warning("Primary grid has neither VDD nor VSS - skipping power distribution")
                    power_dist = None
                elif not secondary_vdd and not secondary_vss:
                    logger.warning("Secondary grid has neither VDD nor VSS - skipping power distribution")
                    power_dist = None
                else:
                    logger.debug("Creating PowerGrid objects...")
                    power_dist = PowerDistribution(
                        primary_grid=PowerGrid(VDD=primary_vdd, VSS=primary_vss),
                        secondary_grid=PowerGrid(VDD=secondary_vdd, VSS=secondary_vss)
                    )
                    logger.debug("Power distribution parsed successfully")
        except Exception as e:
            logger.warning(f"Error parsing power distribution (will skip): {e}")
            logger.debug(f"Full fabric data keys: {list(data.keys())}")
            if 'power_distribution' in data:
                logger.debug(f"Power distribution content: {data['power_distribution']}")
            power_dist = None
    else:
        logger.debug("No power_distribution section found in fabric config")
    
    # Filter known fields for FabricConfiguration
    fabric_fields = {'name', 'description'}
    filtered_fabric_data = {k: v for k, v in data.items() if k in fabric_fields}
    ignored_fabric = set(data.keys()) - fabric_fields - {'array_dimensions', 'tile_configuration', 'edge_cells', 'io_ring', 'margins', 'power_distribution'}
    if ignored_fabric:
        logger.debug(f"Ignoring unknown fabric fields: {ignored_fabric}")
    
    # Ensure name is always present
    if 'name' not in filtered_fabric_data:
        logger.error(f"Fabric configuration missing required 'name' field. Available fields: {list(data.keys())}")
        raise ValueError("Fabric configuration must have a 'name' field")
    
    logger.debug(f"Creating FabricConfiguration with fields: {list(filtered_fabric_data.keys())}")
    
    return FabricConfiguration(
        array_dimensions=array_dims,
        tile_configuration=tile_config,
        edge_cells=edge_cells,
        io_ring=io_ring,
        margins=margins,
        power_distribution=power_dist,
        **filtered_fabric_data
    )


# ============================================================================
# Main Fabric Generator Class
# ============================================================================

class FabricGenerator:
    """Main fabric generator class."""
    
    def __init__(self):
        """Initialize the fabric generator."""
        self.technology: Optional[Technology] = None
        self.tile_definitions: Optional[TileDefinitions] = None
        self.fabric_config: Optional[FabricConfiguration] = None
        self.cell_instances: List[CellInstance] = []
        self.edge_cell_instances: List[CellInstance] = []
        self.placed_pins: List[PlacedPin] = []
        self.dimensions: Optional[FabricDimensions] = None
        self.stats: FabricStats = FabricStats()
        self.tile_array: List[List[str]] = []

    def load_inputs(
        self, 
        tech_file: Path, 
        tiles_file: Path, 
        fabric_file: Path
    ) -> None:
        """Load and validate input files."""
        try:
            # Load technology file
            logger.debug(f"Loading technology file: {tech_file}")
            with open(tech_file, 'r') as f:
                tech_data = json.load(f)
            self.technology = parse_technology(tech_data)
            logger.info(f"Loaded technology: {self.technology.technology} with {len(self.technology.cells)} cells")

            # Load tile definitions
            logger.debug(f"Loading tiles file: {tiles_file}")
            with open(tiles_file, 'r') as f:
                tiles_data = json.load(f)
            self.tile_definitions = parse_tile_definitions(tiles_data)
            logger.info(f"Loaded {len(self.tile_definitions.tiles)} tile definitions")

            # Load fabric configuration
            logger.debug(f"Loading fabric file: {fabric_file}")
            with open(fabric_file, 'r') as f:
                fabric_data = json.load(f)
            self.fabric_config = parse_fabric_configuration(fabric_data)
            logger.info(f"Loaded fabric configuration: {self.fabric_config.name}")

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in input files: {e}")
            raise
        except KeyError as e:
            logger.error(f"Missing required field in input files: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading input files: {e}")
            if logger.isEnabledFor(logging.DEBUG):
                import traceback
                traceback.print_exc()
            raise

    def validate_inputs(self) -> None:
        """Validate input consistency."""
        if not all([self.technology, self.tile_definitions, self.fabric_config]):
            raise ValueError("All input files must be loaded before validation")

        # Validate tile row widths using technology data
        logger.debug("Validating tile row widths...")
        for tile in self.tile_definitions.tiles:
            tile.validate_row_widths(self.technology)

        # Validate default tile exists
        default_tile = self.fabric_config.tile_configuration.default_tile
        if not self.tile_definitions.get_tile_by_name(default_tile):
            raise ValueError(f"Default tile '{default_tile}' not found in tile definitions")

        # Validate region tiles exist
        for region in self.fabric_config.tile_configuration.regions:
            if not self.tile_definitions.get_tile_by_name(region.tile_type):
                raise ValueError(f"Region tile '{region.tile_type}' not found in tile definitions")

        # Validate edge cell types exist
        if self.fabric_config.edge_cells:
            for direction, config in [
                ('left', self.fabric_config.edge_cells.left),
                ('right', self.fabric_config.edge_cells.right),
                ('top', self.fabric_config.edge_cells.top),
                ('bottom', self.fabric_config.edge_cells.bottom)
            ]:
                if config and config.enable:
                    if not self.technology.get_cell_by_alias(config.cell):
                        raise ValueError(f"Edge cell '{config.cell}' for {direction} edge not found in technology")

        # Validate regions don't overlap and are within bounds
        self._validate_regions()

        logger.info("Input validation completed successfully")

    def _validate_regions(self) -> None:
        """Validate region boundaries and overlaps."""
        array_rows = self.fabric_config.array_dimensions.rows
        array_cols = self.fabric_config.array_dimensions.cols
        
        regions = self.fabric_config.tile_configuration.regions
        for i, region in enumerate(regions):
            area = region.area
            
            # Check boundaries
            if (area['row_start'] + area['height'] > array_rows or
                area['col_start'] + area['width'] > array_cols):
                raise ValueError(f"Region '{region.name}' extends beyond fabric boundaries")
            
            # Check for overlaps with other regions
            for j, other_region in enumerate(regions[i+1:], i+1):
                if self._regions_overlap(region.area, other_region.area):
                    raise ValueError(f"Regions '{region.name}' and '{other_region.name}' overlap")

    def _regions_overlap(self, area1: Dict[str, int], area2: Dict[str, int]) -> bool:
        """Check if two regions overlap."""
        r1_left = area1['col_start']
        r1_right = area1['col_start'] + area1['width']
        r1_top = area1['row_start']
        r1_bottom = area1['row_start'] + area1['height']
        
        r2_left = area2['col_start']
        r2_right = area2['col_start'] + area2['width']
        r2_top = area2['row_start']
        r2_bottom = area2['row_start'] + area2['height']
        
        return not (r1_right <= r2_left or r2_right <= r1_left or 
                   r1_bottom <= r2_top or r2_bottom <= r1_top)

    def generate_fabric(self) -> None:
        """Generate the complete fabric."""
        self._initialize_tile_array()
        self._apply_regional_overrides()
        self._calculate_dimensions()
        self._generate_fabric_cells()
        self._generate_edge_cells()
        self._place_io_pins()
        self._calculate_statistics()
        
        logger.info("Fabric generation completed successfully")

    def _initialize_tile_array(self) -> None:
        """Initialize tile array with default tiles."""
        rows = self.fabric_config.array_dimensions.rows
        cols = self.fabric_config.array_dimensions.cols
        default_tile = self.fabric_config.tile_configuration.default_tile
        
        self.tile_array = [[default_tile for _ in range(cols)] for _ in range(rows)]
        logger.debug(f"Initialized {rows}x{cols} tile array with default tile '{default_tile}'")

    def _apply_regional_overrides(self) -> None:
        """Apply regional tile overrides."""
        for region in self.fabric_config.tile_configuration.regions:
            area = region.area
            for row in range(area['row_start'], area['row_start'] + area['height']):
                for col in range(area['col_start'], area['col_start'] + area['width']):
                    self.tile_array[row][col] = region.tile_type
            
            logger.debug(f"Applied region '{region.name}' with tile '{region.tile_type}'")

    def _calculate_dimensions(self) -> None:
        """Calculate fabric dimensions."""
        array_rows = self.fabric_config.array_dimensions.rows
        array_cols = self.fabric_config.array_dimensions.cols
        
        # Get default tile dimensions
        default_tile_name = self.fabric_config.tile_configuration.default_tile
        default_tile = self.tile_definitions.get_tile_by_name(default_tile_name)
        
        # Calculate fabric dimensions in sites/rows
        fabric_rows = array_rows * default_tile.height
        fabric_sites = array_cols * default_tile.width
        
        # Calculate edge cell contributions
        edge_width_left = 0
        edge_width_right = 0
        edge_height_top = 0
        edge_height_bottom = 0
        
        if self.fabric_config.edge_cells:
            if self.fabric_config.edge_cells.left and self.fabric_config.edge_cells.left.enable:
                cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.left.cell)
                edge_width_left = cell.width
            
            if self.fabric_config.edge_cells.right and self.fabric_config.edge_cells.right.enable:
                cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.right.cell)
                edge_width_right = cell.width
            
            if self.fabric_config.edge_cells.top and self.fabric_config.edge_cells.top.enable:
                cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.top.cell)
                edge_height_top = cell.height
                
            if self.fabric_config.edge_cells.bottom and self.fabric_config.edge_cells.bottom.enable:
                cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.bottom.cell)
                edge_height_bottom = cell.height
        
        # Calculate physical dimensions
        site_width = self.technology.site.width
        site_height = self.technology.site.height
        
        core_width = (fabric_sites + edge_width_left + edge_width_right) * site_width
        core_height = (fabric_rows + edge_height_top + edge_height_bottom) * site_height
        
        # Add margins if specified
        margin_h = self.fabric_config.margins.horizontal if self.fabric_config.margins else 0.0
        margin_v = self.fabric_config.margins.vertical if self.fabric_config.margins else 0.0
        
        die_width = core_width + 2 * margin_h
        die_height = core_height + 2 * margin_v
        
        self.dimensions = FabricDimensions(
            tile_array_rows=array_rows,
            tile_array_cols=array_cols,
            fabric_rows=fabric_rows,
            fabric_sites=fabric_sites,
            core_width=core_width,
            core_height=core_height,
            die_width=die_width,
            die_height=die_height,
            margin_horizontal=margin_h,
            margin_vertical=margin_v
        )
        
        logger.info(f"Calculated dimensions - Core: {core_width:.2f}x{core_height:.2f}μm, "
                   f"Die: {die_width:.2f}x{die_height:.2f}μm")

    def _generate_fabric_cells(self) -> None:
        """Generate fabric cell instances."""
        site_width = self.technology.site.width
        site_height = self.technology.site.height
        
        # Calculate starting offsets (margins + left edge cells)
        x_offset = self.dimensions.margin_horizontal
        y_offset = self.dimensions.margin_vertical
        
        if self.fabric_config.edge_cells and self.fabric_config.edge_cells.left and self.fabric_config.edge_cells.left.enable:
            left_cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.left.cell)
            x_offset += left_cell.width * site_width
        
        if self.fabric_config.edge_cells and self.fabric_config.edge_cells.bottom and self.fabric_config.edge_cells.bottom.enable:
            bottom_cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.bottom.cell)
            y_offset += bottom_cell.height * site_height
        
        # Generate cells for each tile
        for tile_row in range(len(self.tile_array)):
            for tile_col in range(len(self.tile_array[0])):
                tile_name = self.tile_array[tile_row][tile_col]
                tile = self.tile_definitions.get_tile_by_name(tile_name)
                
                self._generate_tile_cells(tile, tile_row, tile_col, x_offset, y_offset)

    def _generate_tile_cells(
        self, 
        tile: Tile, 
        tile_row: int, 
        tile_col: int, 
        x_offset: float, 
        y_offset: float
    ) -> None:
        """Generate cells for a specific tile."""
        site_width = self.technology.site.width
        site_height = self.technology.site.height
        
        # Calculate tile base position
        tile_x = x_offset + tile_col * tile.width * site_width
        tile_y = y_offset + tile_row * tile.height * site_height
        
        # Generate cells for each row in the tile
        for row_spec in tile.rows:
            row_y = tile_y + row_spec.row_id * site_height
            cell_x = tile_x
            
            cell_position = 0
            for cell_spec in row_spec.cells:
                cell_def = self.technology.get_cell_by_alias(cell_spec.type)
                if not cell_def:
                    raise ValueError(f"Cell type '{cell_spec.type}' not found in technology")
                
                for i in range(cell_spec.count):
                    instance_name = f"{cell_spec.type}_T{tile_row}-{tile_col}_C{row_spec.row_id}-{cell_position}"
                    
                    cell_instance = CellInstance(
                        name=instance_name,
                        cell_type=cell_def.name,
                        x=cell_x,
                        y=row_y,
                        width=cell_def.width * site_width,
                        height=cell_def.height * site_height,
                        tile_pos=(tile_row, tile_col),
                        cell_pos=(row_spec.row_id, cell_position)
                    )
                    
                    self.cell_instances.append(cell_instance)
                    
                    cell_x += cell_def.width * site_width
                    cell_position += 1

    def _generate_edge_cells(self) -> None:
        """Generate edge cell instances."""
        if not self.fabric_config.edge_cells:
            return
        
        # Left edge cells
        if self.fabric_config.edge_cells.left and self.fabric_config.edge_cells.left.enable:
            self._generate_left_edge_cells()
        
        # Right edge cells
        if self.fabric_config.edge_cells.right and self.fabric_config.edge_cells.right.enable:
            self._generate_right_edge_cells()
        
        # Top edge cells
        if self.fabric_config.edge_cells.top and self.fabric_config.edge_cells.top.enable:
            self._generate_top_edge_cells()
        
        # Bottom edge cells
        if self.fabric_config.edge_cells.bottom and self.fabric_config.edge_cells.bottom.enable:
            self._generate_bottom_edge_cells()

    def _generate_left_edge_cells(self) -> None:
        """Generate left edge cells."""
        cell_alias = self.fabric_config.edge_cells.left.cell
        cell_def = self.technology.get_cell_by_alias(cell_alias)
        
        site_width = self.technology.site.width
        site_height = self.technology.site.height
        
        x = self.dimensions.margin_horizontal
        y_start = self.dimensions.margin_vertical
        
        # Add bottom edge cell height if enabled
        if self.fabric_config.edge_cells.bottom and self.fabric_config.edge_cells.bottom.enable:
            bottom_cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.bottom.cell)
            y_start += bottom_cell.height * site_height
        
        for i in range(self.dimensions.fabric_rows):
            instance_name = f"{cell_alias}_EDGE_LEFT_{i}"
            y = y_start + i * site_height
            
            edge_cell = CellInstance(
                name=instance_name,
                cell_type=cell_def.name,
                x=x,
                y=y,
                width=cell_def.width * site_width,
                height=cell_def.height * site_height,
                is_edge_cell=True,
                edge_direction="left"
            )
            
            self.edge_cell_instances.append(edge_cell)

    def _generate_right_edge_cells(self) -> None:
        """Generate right edge cells."""
        cell_alias = self.fabric_config.edge_cells.right.cell
        cell_def = self.technology.get_cell_by_alias(cell_alias)
        
        site_width = self.technology.site.width
        site_height = self.technology.site.height
        
        # Calculate x position
        x = self.dimensions.margin_horizontal + self.dimensions.fabric_sites * site_width
        
        # Add left edge cell width if enabled
        if self.fabric_config.edge_cells.left and self.fabric_config.edge_cells.left.enable:
            left_cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.left.cell)
            x += left_cell.width * site_width
        
        y_start = self.dimensions.margin_vertical
        
        # Add bottom edge cell height if enabled
        if self.fabric_config.edge_cells.bottom and self.fabric_config.edge_cells.bottom.enable:
            bottom_cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.bottom.cell)
            y_start += bottom_cell.height * site_height
        
        for i in range(self.dimensions.fabric_rows):
            instance_name = f"{cell_alias}_EDGE_RIGHT_{i}"
            y = y_start + i * site_height
            
            edge_cell = CellInstance(
                name=instance_name,
                cell_type=cell_def.name,
                x=x,
                y=y,
                width=cell_def.width * site_width,
                height=cell_def.height * site_height,
                is_edge_cell=True,
                edge_direction="right"
            )
            
            self.edge_cell_instances.append(edge_cell)

    def _generate_top_edge_cells(self) -> None:
        """Generate top edge cells."""
        cell_alias = self.fabric_config.edge_cells.top.cell
        cell_def = self.technology.get_cell_by_alias(cell_alias)
        
        site_width = self.technology.site.width
        site_height = self.technology.site.height
        
        # Calculate total width including left/right edge cells
        total_sites = self.dimensions.fabric_sites
        if self.fabric_config.edge_cells.left and self.fabric_config.edge_cells.left.enable:
            left_cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.left.cell)
            total_sites += left_cell.width
        if self.fabric_config.edge_cells.right and self.fabric_config.edge_cells.right.enable:
            right_cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.right.cell)
            total_sites += right_cell.width
        
        # Calculate y position (top of fabric)
        y = self.dimensions.margin_vertical + self.dimensions.fabric_rows * site_height
        if self.fabric_config.edge_cells.bottom and self.fabric_config.edge_cells.bottom.enable:
            bottom_cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.bottom.cell)
            y += bottom_cell.height * site_height
        
        x = self.dimensions.margin_horizontal
        
        # Generate cells to span the width
        cells_needed = (total_sites + cell_def.width - 1) // cell_def.width  # Ceiling division
        
        for i in range(cells_needed):
            instance_name = f"{cell_alias}_EDGE_TOP_{i}"
            cell_x = x + i * cell_def.width * site_width
            
            edge_cell = CellInstance(
                name=instance_name,
                cell_type=cell_def.name,
                x=cell_x,
                y=y,
                width=cell_def.width * site_width,
                height=cell_def.height * site_height,
                is_edge_cell=True,
                edge_direction="top"
            )
            
            self.edge_cell_instances.append(edge_cell)

    def _generate_bottom_edge_cells(self) -> None:
        """Generate bottom edge cells."""
        cell_alias = self.fabric_config.edge_cells.bottom.cell
        cell_def = self.technology.get_cell_by_alias(cell_alias)
        
        site_width = self.technology.site.width
        site_height = self.technology.site.height
        
        # Calculate total width including left/right edge cells
        total_sites = self.dimensions.fabric_sites
        if self.fabric_config.edge_cells.left and self.fabric_config.edge_cells.left.enable:
            left_cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.left.cell)
            total_sites += left_cell.width
        if self.fabric_config.edge_cells.right and self.fabric_config.edge_cells.right.enable:
            right_cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.right.cell)
            total_sites += right_cell.width
        
        y = self.dimensions.margin_vertical
        x = self.dimensions.margin_horizontal
        
        # Generate cells to span the width
        cells_needed = (total_sites + cell_def.width - 1) // cell_def.width  # Ceiling division
        
        for i in range(cells_needed):
            instance_name = f"{cell_alias}_EDGE_BOTTOM_{i}"
            cell_x = x + i * cell_def.width * site_width
            
            edge_cell = CellInstance(
                name=instance_name,
                cell_type=cell_def.name,
                x=cell_x,
                y=y,
                width=cell_def.width * site_width,
                height=cell_def.height * site_height,
                is_edge_cell=True,
                edge_direction="bottom"
            )
            
            self.edge_cell_instances.append(edge_cell)

    def _place_io_pins(self) -> None:
        """Place I/O pins around the fabric edges."""
        if not self.fabric_config.io_ring or not self.fabric_config.io_ring.edges:
            return
        
        pin_size = self.fabric_config.io_ring.pin_size
        
        for edge_name, edge_config in self.fabric_config.io_ring.edges.items():
            if edge_config.spacing == "auto":
                self._place_auto_pins(edge_name, edge_config, pin_size)
            else:  # manual
                self._place_manual_pins(edge_name, edge_config, pin_size)

    def _place_auto_pins(self, edge_name: str, edge_config: IOEdge, pin_size: PinSize) -> None:
        """Place pins with automatic spacing."""
        if not edge_config.pins:
            return
        
        margin_h = self.dimensions.margin_horizontal
        margin_v = self.dimensions.margin_vertical
        
        if edge_name in ["north", "south"]:
            available_width = self.dimensions.die_width - 2 * margin_h
            spacing = available_width / (len(edge_config.pins) + 1)
            
            for i, pin in enumerate(edge_config.pins):
                x = margin_h + (i + 1) * spacing - pin_size.width / 2
                y = 0 if edge_name == "south" else self.dimensions.die_height - pin_size.height
                
                placed_pin = PlacedPin(
                    name=pin.name,
                    direction=pin.direction,
                    pin_type=pin.type,
                    edge=edge_name,
                    x=x,
                    y=y,
                    width=pin_size.width,
                    height=pin_size.height
                )
                self.placed_pins.append(placed_pin)
        
        else:  # east, west
            available_height = self.dimensions.die_height - 2 * margin_v
            spacing = available_height / (len(edge_config.pins) + 1)
            
            for i, pin in enumerate(edge_config.pins):
                x = 0 if edge_name == "west" else self.dimensions.die_width - pin_size.width
                y = margin_v + (i + 1) * spacing - pin_size.height / 2
                
                placed_pin = PlacedPin(
                    name=pin.name,
                    direction=pin.direction,
                    pin_type=pin.type,
                    edge=edge_name,
                    x=x,
                    y=y,
                    width=pin_size.width,
                    height=pin_size.height
                )
                self.placed_pins.append(placed_pin)

    def _place_manual_pins(self, edge_name: str, edge_config: IOEdge, pin_size: PinSize) -> None:
        """Place pins with manual positioning."""
        for pin in edge_config.pins:
            if pin.position is None:
                raise ValueError(f"Pin {pin.name} missing position in manual mode")
            
            # Calculate pin coordinates based on edge and position
            if edge_name == "north":
                x = pin.position - pin_size.width / 2
                y = self.dimensions.die_height - pin_size.height
            elif edge_name == "south":
                x = pin.position - pin_size.width / 2
                y = 0
            elif edge_name == "east":
                x = self.dimensions.die_width - pin_size.width
                y = pin.position - pin_size.height / 2
            else:  # west
                x = 0
                y = pin.position - pin_size.height / 2
            
            # Validate pin is within margins
            self._validate_pin_position(pin.name, edge_name, x, y, pin_size)
            
            placed_pin = PlacedPin(
                name=pin.name,
                direction=pin.direction,
                pin_type=pin.type,
                edge=edge_name,
                x=x,
                y=y,
                width=pin_size.width,
                height=pin_size.height
            )
            self.placed_pins.append(placed_pin)

    def _validate_pin_position(
        self, 
        pin_name: str, 
        edge: str, 
        x: float, 
        y: float, 
        pin_size: PinSize
    ) -> None:
        """Validate pin position is within margin boundaries."""
        margin_h = self.dimensions.margin_horizontal
        margin_v = self.dimensions.margin_vertical
        
        if edge in ["north", "south"]:
            if x < margin_h or x + pin_size.width > self.dimensions.die_width - margin_h:
                raise ValueError(f"Pin {pin_name} extends outside margin boundaries")
        else:
            if y < margin_v or y + pin_size.height > self.dimensions.die_height - margin_v:
                raise ValueError(f"Pin {pin_name} extends outside margin boundaries")

    def _calculate_statistics(self) -> None:
        """Calculate fabric statistics."""
        # Count fabric cells by type
        for cell in self.cell_instances:
            # Extract cell alias from cell_type (reverse lookup)
            cell_alias = self._get_cell_alias(cell.cell_type)
            if cell_alias:
                self.stats.cell_counts[cell_alias] = self.stats.cell_counts.get(cell_alias, 0) + 1
                self.stats.total_cells += 1
        
        # Count edge cells by type
        for edge_cell in self.edge_cell_instances:
            cell_alias = self._get_cell_alias(edge_cell.cell_type)
            if cell_alias:
                edge_key = f"{cell_alias}_{edge_cell.edge_direction}"
                self.stats.edge_cell_counts[edge_key] = self.stats.edge_cell_counts.get(edge_key, 0) + 1
                self.stats.total_edge_cells += 1
        
        # Calculate combined cell counts (fabric + edge cells) and total leakage power
        logger.debug("Calculating combined statistics and leakage power...")
        all_cell_instances = self.cell_instances + self.edge_cell_instances
        
        for cell_instance in all_cell_instances:
            cell_alias = self._get_cell_alias(cell_instance.cell_type)
            if cell_alias:
                # Group DECAP* cells together
                display_type = self._normalize_cell_type(cell_alias)
                self.stats.combined_cell_counts[display_type] = self.stats.combined_cell_counts.get(display_type, 0) + 1
                
                # Add leakage power
                cell_def = self.technology.get_cell_by_alias(cell_alias)
                if cell_def:
                    if cell_def.power and hasattr(cell_def.power, 'leakage') and cell_def.power.leakage is not None:
                        # Convert from technology units to watts (assuming leakage is in uW)
                        leakage_watts = cell_def.power.leakage * 1e-6  # Convert uW to W
                        self.stats.total_leakage_power += leakage_watts
                        logger.debug(f"Cell {cell_alias}: leakage = {cell_def.power.leakage} uW")
                    else:
                        logger.debug(f"Cell {cell_alias}: no power data available")
                else:
                    logger.debug(f"Cell {cell_alias}: cell definition not found")
        
        logger.debug(f"Total combined cell counts: {self.stats.combined_cell_counts}")
        logger.debug(f"Total leakage power: {self.stats.total_leakage_power} W")
        
        # Calculate areas
        self.stats.fabric_area_um2 = self.dimensions.core_width * self.dimensions.core_height
        self.stats.die_area_um2 = self.dimensions.die_width * self.dimensions.die_height

    def _normalize_cell_type(self, cell_alias: str) -> str:
        """Normalize cell type for statistics (group DECAP* together)."""
        if cell_alias.upper().startswith('DECAP'):
            return 'DECAP'
        return cell_alias

    def _get_cell_alias(self, cell_name: str) -> Optional[str]:
        """Get cell alias from cell name."""
        for cell in self.technology.cells:
            if cell.name == cell_name:
                return cell.alias
        return None

    # ========================================================================
    # Output Generation Methods
    # ========================================================================

    def generate_def_file(self, output_path: Path) -> None:
        """Generate DEF file output."""
        with open(output_path, 'w') as f:
            self._write_def_header(f)
            self._write_def_rows(f)
            self._write_def_components(f)
            self._write_def_pins(f)
            self._write_def_footer(f)
        
        logger.info(f"Generated DEF file: {output_path}")

    def _write_def_header(self, f) -> None:
        """Write DEF file header."""
        units = self.technology.units.distance
        die_width = int(self.dimensions.die_width * units)
        die_height = int(self.dimensions.die_height * units)
        
        f.write(f"VERSION 5.8 ;\n")
        f.write(f"DIVIDERCHAR \"/\" ;\n")
        f.write(f"BUSBITCHARS \"[]\" ;\n")
        f.write(f"DESIGN {self.fabric_config.name} ;\n")
        f.write(f"UNITS DISTANCE MICRONS {units} ;\n")
        f.write(f"DIEAREA ( 0 0 ) ( {die_width} {die_height} ) ;\n\n")

    def _write_def_rows(self, f) -> None:
        """Write DEF row definitions."""
        site_name = self.technology.site.name
        site_width = int(self.technology.site.width * self.technology.units.distance)
        site_height = int(self.technology.site.height * self.technology.units.distance)
        
        row_count = 0
        
        # Bottom edge row if enabled
        if (self.fabric_config.edge_cells and 
            self.fabric_config.edge_cells.bottom and 
            self.fabric_config.edge_cells.bottom.enable):
            
            x_offset = int(self.dimensions.margin_horizontal * self.technology.units.distance)
            y_offset = int(self.dimensions.margin_vertical * self.technology.units.distance)
            
            f.write(f"ROW ROW_BOTTOM_{row_count} {site_name} {x_offset} {y_offset} N "
                   f"DO {self.dimensions.fabric_sites} BY 1 STEP {site_width} 0 ;\n")
            row_count += 1
        
        # Main fabric rows
        for i in range(self.dimensions.fabric_rows):
            x_offset = int(self.dimensions.margin_horizontal * self.technology.units.distance)
            y_offset = int((self.dimensions.margin_vertical + 
                           (i + (1 if self.fabric_config.edge_cells and 
                                    self.fabric_config.edge_cells.bottom and 
                                    self.fabric_config.edge_cells.bottom.enable else 0)) * 
                           self.technology.site.height) * self.technology.units.distance)
            
            f.write(f"ROW ROW_{i} {site_name} {x_offset} {y_offset} N "
                   f"DO {self.dimensions.fabric_sites} BY 1 STEP {site_width} 0 ;\n")
        
        # Top edge row if enabled
        if (self.fabric_config.edge_cells and 
            self.fabric_config.edge_cells.top and 
            self.fabric_config.edge_cells.top.enable):
            
            x_offset = int(self.dimensions.margin_horizontal * self.technology.units.distance)
            y_offset = int((self.dimensions.margin_vertical + 
                           (self.dimensions.fabric_rows + 
                            (1 if self.fabric_config.edge_cells and 
                                 self.fabric_config.edge_cells.bottom and 
                                 self.fabric_config.edge_cells.bottom.enable else 0)) * 
                           self.technology.site.height) * self.technology.units.distance)
            
            f.write(f"ROW ROW_TOP_{row_count} {site_name} {x_offset} {y_offset} N "
                   f"DO {self.dimensions.fabric_sites} BY 1 STEP {site_width} 0 ;\n")
        
        f.write("\n")

    def _write_def_components(self, f) -> None:
        """Write DEF component definitions."""
        all_components = self.cell_instances + self.edge_cell_instances
        
        f.write(f"COMPONENTS {len(all_components)} ;\n")
        
        units = self.technology.units.distance
        
        for component in all_components:
            x = int(component.x * units)
            y = int(component.y * units)
            f.write(f"  - {component.name} {component.cell_type} + PLACED ( {x} {y} ) N ;\n")
        
        f.write("END COMPONENTS\n\n")

    def _write_def_pins(self, f) -> None:
        """Write DEF pin definitions."""
        if not self.placed_pins:
            return
        
        f.write(f"PINS {len(self.placed_pins)} ;\n")
        
        units = self.technology.units.distance
        
        for pin in self.placed_pins:
            direction = pin.direction.upper()
            x1 = int(pin.x * units)
            y1 = int(pin.y * units)
            x2 = int((pin.x + pin.width) * units)
            y2 = int((pin.y + pin.height) * units)
            
            f.write(f"  - {pin.name} + NET {pin.name} + DIRECTION {direction} + USE SIGNAL\n")
            f.write(f"    + LAYER met5 ( {x1} {y1} ) ( {x2} {y2} )\n")
            f.write(f"    + PLACED ( {x1} {y1} ) N ;\n")
        
        f.write("END PINS\n\n")

    def _write_def_footer(self, f) -> None:
        """Write DEF file footer."""
        f.write("END DESIGN\n")

    def generate_lef_file(self, output_path: Path) -> None:
        """Generate LEF file output."""
        with open(output_path, 'w') as f:
            self._write_lef_header(f)
            self._write_lef_macro(f)
        
        logger.info(f"Generated LEF file: {output_path}")

    def _write_lef_header(self, f) -> None:
        """Write LEF file header."""
        f.write(f"VERSION 5.8 ;\n")
        f.write(f"BUSBITCHARS \"[]\" ;\n")
        f.write(f"DIVIDERCHAR \"/\" ;\n\n")
        
        f.write(f"UNITS\n")
        f.write(f"  DATABASE MICRONS {self.technology.units.distance} ;\n")
        f.write(f"END UNITS\n\n")

    def _write_lef_macro(self, f) -> None:
        """Write LEF macro definition."""
        f.write(f"MACRO {self.fabric_config.name}\n")
        f.write(f"  CLASS BLOCK ;\n")
        f.write(f"  ORIGIN 0 0 ;\n")
        f.write(f"  FOREIGN {self.fabric_config.name} 0 0 ;\n")
        f.write(f"  SIZE {self.dimensions.die_width:.3f} BY {self.dimensions.die_height:.3f} ;\n")
        
        # Write pins
        for pin in self.placed_pins:
            f.write(f"  PIN {pin.name}\n")
            f.write(f"    DIRECTION {pin.direction.upper()} ;\n")
            f.write(f"    USE SIGNAL ;\n")
            f.write(f"    PORT\n")
            f.write(f"      LAYER met5 ;\n")
            f.write(f"        RECT {pin.x:.3f} {pin.y:.3f} "
                   f"{pin.x + pin.width:.3f} {pin.y + pin.height:.3f} ;\n")
            f.write(f"    END\n")
            f.write(f"  END {pin.name}\n")
        
        f.write(f"END {self.fabric_config.name}\n\n")
        f.write(f"END LIBRARY\n")

    def generate_json_file(self, output_path: Path) -> None:
        """Generate JSON output file."""
        output_data = {
            "fabric_name": self.fabric_config.name,
            "dimensions": {
                "tile_array": {
                    "rows": self.dimensions.tile_array_rows,
                    "cols": self.dimensions.tile_array_cols
                },
                "fabric": {
                    "rows": self.dimensions.fabric_rows,
                    "sites": self.dimensions.fabric_sites
                },
                "core_area": {
                    "width_um": self.dimensions.core_width,
                    "height_um": self.dimensions.core_height
                },
                "die_area": {
                    "width_um": self.dimensions.die_width,
                    "height_um": self.dimensions.die_height
                },
                "margins": {
                    "horizontal_um": self.dimensions.margin_horizontal,
                    "vertical_um": self.dimensions.margin_vertical
                }
            },
            "statistics": {
                "fabric_cells": self.stats.cell_counts,
                "edge_cells": self.stats.edge_cell_counts,
                "combined_cell_counts": self.stats.combined_cell_counts,
                "total_fabric_cells": self.stats.total_cells,
                "total_edge_cells": self.stats.total_edge_cells,
                "total_leakage_power_watts": self.stats.total_leakage_power,
                "fabric_area_um2": self.stats.fabric_area_um2,
                "die_area_um2": self.stats.die_area_um2
            },
            "io_pins": [
                {
                    "name": pin.name,
                    "direction": pin.direction,
                    "type": pin.pin_type,
                    "edge": pin.edge,
                    "position": {
                        "x_um": pin.x,
                        "y_um": pin.y,
                        "width_um": pin.width,
                        "height_um": pin.height
                    }
                }
                for pin in self.placed_pins
            ],
            "tile_array": self.tile_array
        }
        
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        logger.info(f"Generated JSON file: {output_path}")

    def generate_svg_files(self, output_dir: Path) -> None:
        """Generate SVG visualization files."""
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("Matplotlib not available - skipping SVG generation")
            return
        
        # Generate fabric visualization
        self._generate_fabric_svg(output_dir / f"{self.fabric_config.name}.svg")
        
        # Generate tile visualizations
        used_tiles = set()
        for row in self.tile_array:
            used_tiles.update(row)
        
        for tile_name in used_tiles:
            self._generate_tile_svg(tile_name, output_dir / f"tile_{tile_name}.svg")

    def _generate_fabric_svg(self, output_path: Path) -> None:
        """Generate fabric visualization PNG."""
        fig, ax = plt.subplots(1, 1, figsize=(12, 8))
        
        # Draw die area boundary (red)
        die_rect = Rectangle(
            (0, 0), 
            self.dimensions.die_width, 
            self.dimensions.die_height,
            linewidth=2, 
            edgecolor='red', 
            facecolor='none'
        )
        ax.add_patch(die_rect)
        
        # Draw core area boundary (blue)
        core_rect = Rectangle(
            (self.dimensions.margin_horizontal, self.dimensions.margin_vertical),
            self.dimensions.core_width,
            self.dimensions.core_height,
            linewidth=2,
            edgecolor='blue',
            facecolor='none'
        )
        ax.add_patch(core_rect)
        
        # Draw tiles
        tile_count = self.dimensions.tile_array_rows * self.dimensions.tile_array_cols
        if tile_count > 100:  # Large fabrics need smaller fonts
            font_scale = 0.6
        elif tile_count > 25:  # Medium fabrics
            font_scale = 0.8
        else:  # Small fabrics can use larger fonts
            font_scale = 1.0
            
        self._draw_tiles(ax, font_scale)
        
        # Draw edge cells
        self._draw_edge_cells(ax)
        
        # Draw I/O pins
        self._draw_io_pins(ax, font_scale)
        
        # Set equal aspect ratio and limits
        ax.set_aspect('equal')
        ax.set_xlim(-self.dimensions.die_width * 0.1, self.dimensions.die_width * 1.1)
        ax.set_ylim(-self.dimensions.die_height * 0.1, self.dimensions.die_height * 1.1)
        
        # Add title and labels
        ax.set_title(f"Fabric: {self.fabric_config.name}")
        ax.set_xlabel("X (μm)")
        ax.set_ylabel("Y (μm)")
        
        # Add legend
        self._add_fabric_legend(ax)
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"Generated fabric PNG: {output_path}")

    def _draw_tiles(self, ax, font_scale: float = 1.0) -> None:
        """Draw tile rectangles on the fabric visualization."""
        site_width = self.technology.site.width
        site_height = self.technology.site.height
        
        # Color map for different tile types
        tile_colors = {}
        colors = ['lightblue', 'lightgreen', 'lightyellow', 'lightcoral', 'lightpink', 
                 'lightsteelblue', 'lightcyan', 'lavender', 'mistyrose', 'honeydew']
        
        x_offset = self.dimensions.margin_horizontal
        y_offset = self.dimensions.margin_vertical
        
        # Add left edge cell offset
        if self.fabric_config.edge_cells and self.fabric_config.edge_cells.left and self.fabric_config.edge_cells.left.enable:
            left_cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.left.cell)
            x_offset += left_cell.width * site_width
        
        # Add bottom edge cell offset
        if self.fabric_config.edge_cells and self.fabric_config.edge_cells.bottom and self.fabric_config.edge_cells.bottom.enable:
            bottom_cell = self.technology.get_cell_by_alias(self.fabric_config.edge_cells.bottom.cell)
            y_offset += bottom_cell.height * site_height
        
        for tile_row in range(len(self.tile_array)):
            for tile_col in range(len(self.tile_array[0])):
                tile_name = self.tile_array[tile_row][tile_col]
                tile = self.tile_definitions.get_tile_by_name(tile_name)
                
                if tile_name not in tile_colors:
                    tile_colors[tile_name] = colors[len(tile_colors) % len(colors)]
                
                tile_x = x_offset + tile_col * tile.width * site_width
                tile_y = y_offset + tile_row * tile.height * site_height
                tile_width = tile.width * site_width
                tile_height = tile.height * site_height
                
                rect = Rectangle(
                    (tile_x, tile_y),
                    tile_width,
                    tile_height,
                    facecolor=tile_colors[tile_name],
                    edgecolor='black',
                    alpha=0.7
                )
                ax.add_patch(rect)
                
                # Add tile label with adaptive font size
                base_font_size = 8 * font_scale
                min_dimension = min(tile_width, tile_height)
                
                # Scale font based on tile size and overall fabric complexity
                if min_dimension > 20:  # Large tiles
                    font_size = max(6, base_font_size)
                elif min_dimension > 10:  # Medium tiles
                    font_size = max(5, base_font_size * 0.8)
                else:  # Small tiles
                    font_size = max(4, base_font_size * 0.6)
                
                # Only show labels if there's enough space
                if tile_width > 10 and tile_height > 8:
                    ax.text(
                        tile_x + tile_width/2,
                        tile_y + tile_height/2,
                        f"{tile_name}\n({tile_row},{tile_col})",
                        ha='center',
                        va='center',
                        fontsize=font_size,
                        weight='bold' if font_size >= 6 else 'normal'
                    )

    def _draw_edge_cells(self, ax) -> None:
        """Draw edge cells on the fabric visualization."""
        for edge_cell in self.edge_cell_instances:
            rect = Rectangle(
                (edge_cell.x, edge_cell.y),
                edge_cell.width,
                edge_cell.height,
                facecolor='orange',
                edgecolor='black',
                alpha=0.8
            )
            ax.add_patch(rect)

    def _draw_io_pins(self, ax, font_scale: float = 1.0) -> None:
        """Draw I/O pins on the fabric visualization."""
        for pin in self.placed_pins:
            rect = Rectangle(
                (pin.x, pin.y),
                pin.width,
                pin.height,
                facecolor='gold',
                edgecolor='black'
            )
            ax.add_patch(rect)
            
            # Add pin label with adaptive font size
            font_size = max(4, 6 * font_scale)
            
            # Only add label if pin is large enough
            if pin.width > 0.5 and pin.height > 0.5:
                ax.text(
                    pin.x + pin.width/2,
                    pin.y + pin.height/2,
                    pin.name,
                    ha='center',
                    va='center',
                    fontsize=font_size,
                    rotation=90 if pin.edge in ['east', 'west'] else 0,
                    weight='bold' if font_size >= 6 else 'normal'
                )

    def _add_fabric_legend(self, ax) -> None:
        """Add legend to fabric visualization."""
        legend_elements = [
            plt.Line2D([0], [0], color='red', lw=2, label='Die Area'),
            plt.Line2D([0], [0], color='blue', lw=2, label='Core Area'),
            plt.Rectangle((0, 0), 1, 1, facecolor='orange', alpha=0.8, label='Edge Cells'),
            plt.Rectangle((0, 0), 1, 1, facecolor='gold', label='I/O Pins')
        ]
        
        ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1, 1))

    def _generate_tile_svg(self, tile_name: str, output_path: Path) -> None:
        """Generate individual tile visualization SVG."""
        tile = self.tile_definitions.get_tile_by_name(tile_name)
        if not tile:
            return
        
        # Calculate appropriate figure size based on tile dimensions
        site_width = self.technology.site.width
        site_height = self.technology.site.height
        
        tile_aspect_ratio = (tile.width * site_width) / (tile.height * site_height)
        
        # Scale based on tile complexity (number of cells)
        total_cells = sum(sum(cell.count for cell in row.cells) for row in tile.rows)
        
        # For SVG, we can use generous sizes since it's vector-based
        if total_cells <= 50:  # Small tiles
            base_size = 10
        elif total_cells <= 200:  # Medium tiles
            base_size = 14
        elif total_cells <= 500:  # Large tiles
            base_size = 18
        else:  # Very large tiles
            base_size = 22
        
        if tile_aspect_ratio > 1:  # Wider than tall
            fig_width = base_size
            fig_height = fig_width / tile_aspect_ratio
        else:  # Taller than wide
            fig_height = base_size
            fig_width = fig_height * tile_aspect_ratio
        
        fig, ax = plt.subplots(1, 1, figsize=(fig_width, fig_height))
        
        # Draw tile boundary
        tile_rect = Rectangle(
            (0, 0),
            tile.width * site_width,
            tile.height * site_height,
            linewidth=2,
            edgecolor='black',
            facecolor='lightgray',
            alpha=0.3
        )
        ax.add_patch(tile_rect)
        
        # Draw cells in each row
        cell_colors = self._get_cell_color_map()
        
        for row_spec in tile.rows:
            row_y = row_spec.row_id * site_height
            cell_x = 0
            
            for cell_spec in row_spec.cells:
                cell_def = self.technology.get_cell_by_alias(cell_spec.type)
                if not cell_def:
                    continue
                
                color = cell_colors.get(cell_spec.type, 'white')
                
                for i in range(cell_spec.count):
                    cell_width = cell_def.width * site_width
                    cell_height = cell_def.height * site_height
                    
                    rect = Rectangle(
                        (cell_x, row_y),
                        cell_width,
                        cell_height,
                        facecolor=color,
                        edgecolor='black',
                        linewidth=0.5
                    )
                    ax.add_patch(rect)
                    
                    # Add cell label if space permits (adaptive font size)
                    min_font_size = max(4, min(12, base_size * 0.5))
                    if cell_width > 0.8 and cell_height > 0.4:
                        ax.text(
                            cell_x + cell_width/2,
                            row_y + cell_height/2,
                            cell_spec.type,
                            ha='center',
                            va='center',
                            fontsize=min_font_size,
                            weight='bold' if min_font_size >= 8 else 'normal'
                        )
                    
                    cell_x += cell_width
        
        # Draw grid lines with appropriate thickness
        grid_alpha = 0.6 if total_cells > 500 else 0.4
        grid_width = 0.3 if total_cells > 500 else 0.5
        
        for i in range(tile.height + 1):
            ax.axhline(y=i * site_height, color='gray', linewidth=grid_width, alpha=grid_alpha)
        
        for i in range(tile.width + 1):
            ax.axvline(x=i * site_width, color='gray', linewidth=grid_width, alpha=grid_alpha)
        
        ax.set_aspect('equal')
        ax.set_xlim(0, tile.width * site_width)
        ax.set_ylim(0, tile.height * site_height)
        
        # Adaptive font sizes
        title_font_size = max(12, min(20, base_size * 0.8))
        label_font_size = max(10, min(16, base_size * 0.6))
        
        ax.set_title(f"Tile: {tile_name} ({tile.width}×{tile.height} sites, {total_cells} cells)", 
                    fontsize=title_font_size, weight='bold')
        ax.set_xlabel("X (μm)", fontsize=label_font_size)
        ax.set_ylabel("Y (μm)", fontsize=label_font_size)
        
        # Add subtle grid for better readability
        ax.grid(True, alpha=0.2, linewidth=0.3)
        
        plt.tight_layout()
        
        # Save as SVG - vector format
        plt.savefig(output_path, format='svg', bbox_inches='tight')
        plt.close()
        
        logger.info(f"Generated tile SVG: {output_path}")
        logger.info(f"  Figure: {fig_width:.1f}x{fig_height:.1f} inches (vector format)")

    def _get_cell_color_map(self) -> Dict[str, str]:
        """Get color mapping for different cell types."""
        return {
            # Logic cells
            'NAND2': 'lightblue',
            'NOR2': 'lightcyan',
            'INV': 'lightgreen',
            'AND2': 'lightsteelblue',
            'OR2': 'lightcyan',
            'XOR2': 'lightyellow',
            'XNOR2': 'lightgoldenrodyellow',
            'BUF': 'lightgreen',
            'MUX2': 'lightblue',
            
            # Sequential cells
            'DFF': 'yellow',
            'DFFP': 'gold',
            'DFFRP': 'orange',
            'DFFSR': 'darkorange',
            'LATCH': 'orange',
            'DLATCH': 'sandybrown',
            
            # Physical cells
            'TAP': 'gray',
            'CONB': 'darkgray',
            'WELLTAP': 'gray',
            'ENDCAP': 'dimgray',
            
            # Decap cells
            'DECAP1': 'pink',
            'DECAP2': 'pink',
            'DECAP4': 'pink',
            'DECAP6': 'pink',
            'DECAP8': 'pink',
            'DECAP12': 'pink',
            'DECAP16': 'pink',
            
            # Fill and filler cells
            'FILL': 'white',
            'FILLER': 'white',
            'DIODE': 'plum',
            
            # Special cells
            'ANTENNA': 'lightcoral',
            'TIE': 'lightgray'
        }


# ============================================================================
# Command Line Interface
# ============================================================================

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Sky130 Structured ASIC Fabric Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python gen_fabric.py tech.json tiles.json fabric.json
  python gen_fabric.py tech.json tiles.json fabric.json --output-dir output/
  python gen_fabric.py tech.json tiles.json fabric.json --output-name my_fabric
  python gen_fabric.py tech.json tiles.json fabric.json --pin-size 2.0 1.5
        """
    )
    
    parser.add_argument(
        'technology',
        type=Path,
        help='Technology definition JSON file'
    )
    
    parser.add_argument(
        'tiles',
        type=Path,
        help='Tile definitions JSON file'
    )
    
    parser.add_argument(
        'fabric',
        type=Path,
        help='Fabric configuration JSON file'
    )
    
    parser.add_argument(
        '--output-dir',
        type=Path,
        help='Output directory (default: current directory)'
    )
    
    parser.add_argument(
        '--output-name',
        type=str,
        help='Output file base name (default: fabric name)'
    )
    
    parser.add_argument(
        '--pin-size',
        nargs=2,
        type=float,
        metavar=('WIDTH', 'HEIGHT'),
        help='Pin rectangle size in database units'
    )
    
    parser.add_argument(
        '--pin-size-um',
        nargs=2,
        type=float,
        metavar=('WIDTH', 'HEIGHT'),
        help='Pin rectangle size in microns'
    )
    
    parser.add_argument(
        '--def-only',
        action='store_true',
        help='Generate only DEF file'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress non-error output'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='Sky130 Fabric Generator v1.3'
    )
    
    return parser.parse_args()


def setup_logging(verbose: bool, quiet: bool) -> None:
    """Setup logging configuration."""
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    
    logging.getLogger().setLevel(level)


def determine_output_paths(
    args: argparse.Namespace, 
    fabric_name: str
) -> Tuple[Path, str]:
    """Determine output directory and base name."""
    if args.output_dir and args.output_name:
        return args.output_dir, args.output_name
    elif args.output_dir:
        return args.output_dir, args.output_dir.name
    elif args.output_name:
        return Path(args.output_name), args.output_name
    else:
        return Path('.'), fabric_name


def update_pin_size(fabric_config: FabricConfiguration, args: argparse.Namespace) -> None:
    """Update pin size from command line arguments."""
    if args.pin_size:
        if not fabric_config.io_ring:
            fabric_config.io_ring = IORing()
        fabric_config.io_ring.pin_size.width = args.pin_size[0]
        fabric_config.io_ring.pin_size.height = args.pin_size[1]
    elif args.pin_size_um:
        if not fabric_config.io_ring:
            fabric_config.io_ring = IORing()
        fabric_config.io_ring.pin_size.width = args.pin_size_um[0]
        fabric_config.io_ring.pin_size.height = args.pin_size_um[1]


def main() -> int:
    """Main function."""
    try:
        args = parse_arguments()
        setup_logging(args.verbose, args.quiet)
        
        # Create fabric generator
        generator = FabricGenerator()
        
        # Load and validate inputs
        logger.info("Loading input files...")
        generator.load_inputs(args.technology, args.tiles, args.fabric)
        
        # Update pin size from command line if specified
        update_pin_size(generator.fabric_config, args)
        
        logger.info("Validating inputs...")
        generator.validate_inputs()
        
        # Generate fabric
        logger.info("Generating fabric...")
        generator.generate_fabric()
        
        # Determine output paths
        output_dir, base_name = determine_output_paths(args, generator.fabric_config.name)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate outputs
        logger.info(f"Generating outputs in {output_dir}...")
        
        # Always generate DEF file
        generator.generate_def_file(output_dir / f"{base_name}.def")
        
        if not args.def_only:
            generator.generate_lef_file(output_dir / f"{base_name}.lef")
            generator.generate_json_file(output_dir / f"{base_name}.json")
            generator.generate_svg_files(output_dir)
        
        # Print summary
        if not args.quiet:
            print(f"\nFabric Generation Summary:")
            print(f"Fabric: {generator.fabric_config.name}")
            print(f"Dimensions: {generator.dimensions.tile_array_rows}x{generator.dimensions.tile_array_cols} tiles")
            print(f"Core Area: {generator.dimensions.core_width:.2f}x{generator.dimensions.core_height:.2f} μm")
            print(f"Die Area: {generator.dimensions.die_width:.2f}x{generator.dimensions.die_height:.2f} μm")
            print(f"Total Cells: {generator.stats.total_cells}")
            print(f"Edge Cells: {generator.stats.total_edge_cells}")
            print(f"I/O Pins: {len(generator.placed_pins)}")
            
            # Display total leakage power
            if generator.stats.total_leakage_power > 0:
                if generator.stats.total_leakage_power < 1e-3:  # Less than 1mW
                    print(f"Total Leakage Power: {generator.stats.total_leakage_power * 1e6:.2f} μW")
                elif generator.stats.total_leakage_power < 1.0:  # Less than 1W
                    print(f"Total Leakage Power: {generator.stats.total_leakage_power * 1e3:.2f} mW")
                else:
                    print(f"Total Leakage Power: {generator.stats.total_leakage_power:.3f} W")
            else:
                print(f"Total Leakage Power: Not available (no power data in technology file)")
            
            # Display cell counts by type (combined fabric + edge cells)
            if generator.stats.combined_cell_counts:
                print(f"Cell Counts by Type:")
                sorted_counts = sorted(generator.stats.combined_cell_counts.items(), 
                                     key=lambda x: (-x[1], x[0]))  # Sort by count (desc), then name (asc)
                for cell_type, count in sorted_counts:
                    print(f"  {cell_type}: {count}")
            else:
                print(f"Cell Counts by Type: Not available")
            
            # Show cell type breakdown from technology
            cell_types = {}
            for cell in generator.technology.cells:
                cell_types[cell.cell_type] = cell_types.get(cell.cell_type, 0) + 1
            if cell_types:
                print(f"Technology cell types: {dict(cell_types)}")
            
            print(f"Output Directory: {output_dir}")
        
        logger.info("Fabric generation completed successfully")
        return 0
        
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
