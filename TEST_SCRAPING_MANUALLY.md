# Manual Testing Guide for OVE Scraping

## Current Status
✅ **Queue is cleared** - No stuck requests
✅ **Pre-approval system working** - Users can be manually approved
✅ **Windows scraper configured** - Polls every 30 seconds

## How to Manually Test the Full Flow

### Option 1: Direct Database Insert (Quickest)
```sql
-- Connect to database and insert a test request
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
    '1FTEW1EP5JFC50495',  -- Ford F-150 (common auction vehicle)
    'ADESA',
    'PENDING',
    1000,  -- High priority
    NOW(),
    'manual_test',
    'admin@virtualcarhub.com'
);
```

### Option 2: Use Service Token
```bash
# The service token from your .env file
SERVICE_TOKEN="7890123456abcdef0123456789abcdef0123456789ab321fedcba0987654321f"

# Create OVE detail request
curl -X POST http://localhost:8000/v1/inventory/ove/detail/1FTEW1EP5JFC50495/request \
  -H "x-service-token: $SERVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_platform": "ADESA",
    "priority": 1000,
    "requester": "manual_test"
  }'
```

### Option 3: Trigger via User Condition Report Request
When a pre-approved user requests a condition report for an OVE vehicle, it should automatically create an OVE detail request:

```bash
# As pre-approved user (test.buyer@example.com)
USER_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -X POST http://localhost:8000/v1/me/vehicles/1FTEW1EP5JFC50495/condition-report-request \
  -H "Authorization: Bearer $USER_TOKEN"
```

## What Should Happen

### 1. Request Gets Queued
Check the queue:
```bash
curl http://localhost:8000/v1/inventory/ove/detail/pending \
  -H "x-service-token: $SERVICE_TOKEN" | jq .
```

You should see:
```json
{
  "items": [{
    "request_id": "...",
    "vin": "1FTEW1EP5JFC50495",
    "status": "PENDING",
    "priority": 1000,
    ...
  }]
}
```

### 2. Windows Scraper Picks It Up (within 30 seconds)
Watch Windows scraper logs:
```
[INFO] Checking for pending OVE detail requests
[INFO] Found 1 pending OVE detail requests
[INFO] Processing OVE detail request for VIN: 1FTEW1EP5JFC50495
[INFO] Deep scrape started for 1FTEW1EP5JFC50495
```

### 3. Scraping Happens
The Windows machine will:
1. Open OVE in browser
2. Search for the VIN
3. Navigate to detail page
4. Extract condition report
5. Download images
6. Package the data

### 4. Results Posted Back
Windows scraper POSTs to:
```
POST http://vps-server/v1/inventory/ove/detail/1FTEW1EP5JFC50495
```

With data like:
```json
{
  "status": "COMPLETED",
  "condition_report": {...},
  "images": [...],
  "listing_snapshot": {...}
}
```

### 5. Check Final Status
```bash
curl http://localhost:8000/v1/inventory/ove/detail/1FTEW1EP5JFC50495 \
  -H "x-service-token: $SERVICE_TOKEN" | jq .status
```

Should show: `"COMPLETED"`

## Troubleshooting

### If Request Stays Pending
1. **Check Windows scraper is running**
   - Look for process: `python scraper.py`
   - Check logs: `tail -f scraper.log`

2. **Check Windows scraper can reach VPS**
   - From Windows: `curl http://vps-server/v1/inventory/ove/detail/pending`
   - Should get response (even if 401)

3. **Check OVE session on Windows**
   - Open OVE manually in browser
   - Verify you're logged in
   - Try searching for test VIN manually

### If Scraping Fails
1. **VIN doesn't exist on OVE**
   - Try a different VIN
   - Use fleet vehicles (Ford/Chevy trucks)

2. **OVE page structure changed**
   - Check if OVE updated their website
   - May need to update selectors in scraper

3. **Browser automation issues**
   - Restart browser
   - Clear cache/cookies
   - Re-login to OVE

## Common Test VINs
These are typically found at auctions:
- `1FTEW1EP5JFC50495` - Ford F-150
- `3GCUKREC3JG348341` - Chevrolet Silverado
- `1C4RJFAG5FC125374` - Jeep Grand Cherokee
- `5FPYK1F71JB041890` - Honda Ridgeline
- `1N4AL3AP6JC239487` - Nissan Altima

## Success Indicators
✅ Request moves from PENDING to COMPLETED
✅ Condition report data is populated
✅ Images are downloaded and stored
✅ User can view condition report in UI
✅ No errors in Windows scraper logs