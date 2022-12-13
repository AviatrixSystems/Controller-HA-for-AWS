cd ../src/
if [[ "$1" == "--error" ]]; then
    echo "Checking only errors"
    find . -name "*.py" | xargs python3 -m pylint -E
else
    echo "Full pylint check"
    find . -name "*.py" | xargs python3 -m pylint
fi
cd -
