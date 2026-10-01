# get auth token
import requests
import json

url = "https://api.alertsystem.sit.ecvhrm.com/auth/token"

payload = json.dumps({
  "client_id": "aws",
  "client_secret": "J9AuBpRW96NA37K2RkbP"
})
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)


# post mailing
url = "https://api.alertsystem.sit.ecvhrm.com/api/v1/alert/mail"

payload = json.dumps({
  "attachemntId": [],
  "alertLevel": "string",
  "to": [
    "terry.chou@ecloudvalley.com"
  ],
  "body": "test body",
  "cc": [],
  "bcc": [],
  "subject": "test",
  "reporter": "string",
  "importance": "string",
  "emailFrom": "institution.dx@ecloudvalley.com"
})
headers = {
  'Content-Type': 'application/json',
  'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkaXNwbGF5X25hbWUiOiJBV1MtTGFtYmRhIiwicHJvdmlkZXIiOiJBbGVydFN5c3RlbSIsImlhdCI6MTc2NTI0NzAzNiwiZXhwIjoxNzY1MjU0MjM2fQ.oJ8xZL5PpHPWEEHfAS-tQUOBtKf5HNOvFw7sYXshQVM'
}

response = requests.request("POST", url, headers=headers, data=payload)

print(response.text)
 