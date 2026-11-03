WAIT_DELAY = 30
DEV_FLAG = "dev_flag"
TEMP_ACCOUNT_NAME = "tempacc"
# allow up to 3 re-invocations (~60 min total)
MAX_HA_RETRIES = 3
# Shared time reserve for the retried controller APIs
# login / initial_setup / create_temp_account
# Stop retrying and re-invoke the Lambda once less than this much
# time is left, so the next invocation gets a fresh lambda window.
CONTROLLER_API_TIME_RESERVE = 180
# A scale testbed restore take about 6min (QA), and the controller restore process
# is destructive, past a certain point, irreversible. Bump to 660sec for more buffer.
# With less than this much time left, re-invoke and restore in a fresh window.
RESTORE_TIME_RESERVE = 660
