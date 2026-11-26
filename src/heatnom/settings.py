from .exchange_register.contracts import Field

EXPOSURE_UNIT = '保供未覆盖 MWh'
TITLE = '社区热网峰段购热'
ROLE = '区域供热值班员'
OBJECT = '换热片区申报'
TARGET = '峰段购热兆瓦时'
ALGORITHM = '带天气交互的岭回归'
MODE = 'regression'
IS_SURVIVAL = False
MODEL_EPOCH = 'heatnom-1.0'
REGIONS = ('河东片区', '林南片区', '北门片区')
SIGNAL_NAMES = ('degree_area', 'return_deficit', 'windchill', 'reserve_per_area', 'active_floor_area')
RAW_EXPLAIN_INDEX = (None, None, None, None, None)
RESOURCE = '外购热兆瓦时'
DEFAULT_BUDGET = 90
ACTION = '编制峰段申报'
MANUAL_ACTION = '复核表计采样'
NORMAL_ACTION = '现有热源覆盖'
WORKFLOW = '锁定已确认的储热和热源保证量，拆分保供与可中断补量。'
PLACEMENT_MODE = 'firm_first'
POOL_LIMIT = 0
SEPARATE_CONTEXTS = False
HAS_WORKBENCH = False
SAMPLE_NAME = 'heatnom_register.csv'

FIELDS = (
    Field('ambient', '外温', '℃', -17, 12, False),
    Field('area', '供热面积', '万㎡', 4, 75, False),
    Field('return_temp', '回水温度', '℃', 28, 61, False),
    Field('reserve', '储热余量', 'MWh', 0, 46, False),
    Field('wind', '风速', 'm/s', 0, 23, False),
    Field('occupancy', '入住热负荷比例', '%', 34, 99, False),
)
