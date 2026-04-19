"""PowerFactory attribute name constants.

Centralises every PF attribute string so a rename in a PF release
only has to be fixed in one place.
"""

# --- Calculated result variables (require a prior simulation run) -----------
U_PU        = "m:u"        # Bus voltage [p.u.]
I_BUS1_KA   = "m:i1:bus1" # Current at sending terminal [kA]
I_KA        = "m:i1"       # Branch current [kA]
P_BUS1_MW   = "m:P:bus1"  # Active power at sending terminal [MW]
Q_BUS1_MVAR = "m:Q:bus1"  # Reactive power at sending terminal [Mvar]
LOADING_PCT = "c:loading"  # Thermal loading [%]

# --- Model parameter attributes (direct COM attribute access) ---------------
NOM_VOLTAGE_KV = "uknom"        # Nominal voltage [kV]
OUT_OF_SERVICE = "outserv"      # Out-of-service flag (0/1)
I_NOM_KA       = "Inom"         # Rated current — lines [kA]
I_NOM_ALT_KA   = "ratedCurrent" # Rated current — transformers [kA]

# --- Study-case / command object attributes ---------------------------------
QDS_T_START  = "Tstart"        # QDS simulation start time [h]
QDS_T_END    = "Tshow"         # QDS simulation end time [h]
QDS_DT       = "dt"            # QDS time step [h]
STUDY_TIME   = "iStudyTime"    # Study-case reference timestamp
LDF_NOT_CONV = "iopt_notconv"  # Load-flow non-convergence flag
LDF_ITER_CNT = "nrItNum"       # Load-flow iteration count
