# hook-workflow.py
# PyInstaller hook for our local workflow/ module (NOT the PyPI "workflow" package)
# This hook prevents PyInstaller from using the generic "workflow" hook from
# pyinstaller-hooks-contrib which is designed for Prefect's workflow package.


# 明确告诉 PyInstaller 这是本地模块
hiddenimports = [
    'workflow.engine',
    'workflow.gates',
]

# 不收集任何外部数据文件
datas = []
