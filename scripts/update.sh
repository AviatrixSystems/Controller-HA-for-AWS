zip -d ../bin/aviatrix_ha.zip dev_flag
cd ../src
find . -name "*.py"  | grep -Ev "./test/test.py" | zip ../bin/aviatrix_ha.zip -@
cd -

if [[ "$1" == "--dev" ]]; then
    echo "Adding dev_flag" 
    touch dev_flag
    zip ../bin/aviatrix_ha.zip dev_flag 
else
    echo "Not adding dev_flag"
fi
