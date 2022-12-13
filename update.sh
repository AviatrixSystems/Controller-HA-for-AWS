zip -d aviatrix_ha.zip dev_flag 
find . -name "*.py"  | grep -Ev "./test/test.py|./push_to_s3.py" |  zip aviatrix_ha.zip -@

if [[ "$1" == "--dev" ]]; then
    echo "Adding dev_flag" 
    touch dev_flag
    zip aviatrix_ha.zip dev_flag 
else
    echo "Not adding dev_flag"
fi
