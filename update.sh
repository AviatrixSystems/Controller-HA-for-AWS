zip -d dev_flag >/dev/null
zip aviatrix_ha.zip aviatrix_ha.py version.py
if [[ "$1" == "--dev" ]]; then
    echo "Adding dev_flag" 
    touch dev_flag
    zip aviatrix_ha.zip dev_flag 
else
    echo "Not adding dev_flag"
fi
