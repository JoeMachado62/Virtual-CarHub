# Fix Authentication & Test OVE Scraping

## ✅ Status Update

### User Setup Complete
- **User**: joemachado62@live.com
- **User ID**: e97b165f-111a-44d4-a564-c4eb1de2572a
- **Pre-approved**: ✅ YES ($100,000 limit)
- **Deal Status**: PRE_APPROVED
- **Can request condition reports**: ✅ YES

### Browser Auth Issue
The browser has an expired token and no logout button. Here's how to fix it:

## 🔧 Fix Browser Authentication

### Option 1: Clear Browser Storage (Quickest)
1. Open Chrome DevTools (F12)
2. Go to **Application** tab
3. Find **Storage** → **Local Storage** → Your domain
4. Look for keys like:
   - `auth_token`
   - `access_token`
   - `refresh_token`
   - `user`
5. **Delete these keys**
6. Refresh the page
7. Login again with Joe's credentials

### Option 2: Use Console Commands
```javascript
// In browser console, clear auth data:
localStorage.removeItem('auth_token');
localStorage.removeItem('access_token');
localStorage.removeItem('refresh_token');
localStorage.removeItem('user');
sessionStorage.clear();

// Force reload
window.location.reload();
```

### Option 3: Incognito/Private Window
1. Open new Incognito/Private window
2. Navigate to the site
3. Login fresh with Joe's credentials

## 🎯 Test OVE Scraping with Valid VIN

Now let's create a test with a REAL VIN that exists in your database:

### Find a Valid OVE Vehicle
```sql
-- Run this to find valid OVE vehicles in your database
SELECT vin, year, make, model, price_asking
FROM vehicles
WHERE source_type = 'ove'
AND available = true
AND vin NOT LIKE 'W%'  -- Skip Mercedes
ORDER BY updated_at DESC
LIMIT 10;
```

Based on earlier query, these VINs are in your database:
- **1C6SRFFP7TN195518** - 2026 Ram 1500 ($50,000)
- **3VVSC7B20TM006651** - 2026 Volkswagen Taos ($25,000)
- **JTEVB5BR9T5026964** - 2026 Toyota 4Runner ($80,500)

### Create OVE Request via Database
Since the API requires service token, insert directly:

```bash
# Pick one of the valid VINs above
docker exec $(docker ps -q -f name=postgres) psql -U vch -d virtual_carhub -c "
INSERT INTO ove_detail_requests (
    id,
    vin,
    source_platform,
    status,
    priority,
    requested_at,
    request_source,
    requested_by
) VALUES (
    gen_random_uuid(),
    '1C6SRFFP7TN195518',  -- Ram 1500 from your DB
    'ADESA',
    'PENDING',
    999,
    NOW(),
    'joe_test',
    'joemachado62@live.com'
);"
```

### Or Via Condition Report Request (After Login)
Once Joe is logged in with a fresh token:

```javascript
// In browser console after login
fetch('/v1/me/vehicles/1C6SRFFP7TN195518/condition-report-request', {
    method: 'POST',
    headers: {
        'Authorization': 'Bearer ' + localStorage.getItem('access_token'),
        'Content-Type': 'application/json'
    }
})
.then(r => r.json())
.then(data => console.log('Condition report request:', data))
.catch(err => console.error('Error:', err));
```

## 📊 Monitor the Scraping

### 1. Check Queue Status
```bash
docker exec $(docker ps -q -f name=backend) python -c "
from sqlalchemy import create_engine, text
import os
engine = create_engine(os.getenv('DATABASE_URL'))
with engine.connect() as conn:
    result = conn.execute(text('SELECT vin, status, requested_at FROM ove_detail_requests WHERE status = \\'PENDING\\' ORDER BY requested_at DESC'))
    for row in result:
        print(f'VIN: {row[0]} - Status: {row[1]} - Time: {row[2]}')
"
```

### 2. Windows Scraper Logs
The Windows scraper should show:
```
[INFO] Checking for pending OVE detail requests
[INFO] Found 1 pending request
[INFO] Processing VIN: 1C6SRFFP7TN195518
[INFO] Searching OVE for 1C6SRFFP7TN195518
[INFO] Found listing, opening detail page...
```

### 3. Check Completion
After 1-2 minutes:
```bash
docker exec $(docker ps -q -f name=backend) python -c "
from sqlalchemy import create_engine, text
import os
engine = create_engine(os.getenv('DATABASE_URL'))
with engine.connect() as conn:
    result = conn.execute(text('SELECT vin, status FROM ove_detail_requests WHERE vin = \\'1C6SRFFP7TN195518\\''))
    row = result.fetchone()
    if row:
        print(f'VIN: {row[0]} - Status: {row[1]}')
"
```

## ⚠️ Important Notes

1. **Use VINs from your database** - They're already validated as OVE vehicles
2. **Avoid Mercedes VINs** (starting with W) - They failed before
3. **Common auction vehicles work best** - Ram, Ford, Chevy trucks
4. **Windows scraper polls every 30 seconds** - Be patient

## 🚀 Quick Test Sequence

1. **Clear browser auth** (see above)
2. **Login as Joe**
3. **Insert test request** (using SQL above)
4. **Watch Windows scraper logs**
5. **Check status after 2 minutes**

The user is now pre-approved and ready to test! Just need to fix the browser auth issue first.