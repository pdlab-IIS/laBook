#!/bin/bash
deactivate
kill -9 $(lsof -t -i:5000)
sudo systemctl daemon-reload
sudo systemctl restart labook
sudo systemctl restart nginx
sudo systemctl restart ngrok-labook
systemctl status labook nginx ngrok-labook