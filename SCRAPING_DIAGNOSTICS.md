# OVE Scraping System Diagnostics

## Architecture Overview
```
[User Request] → [VPS Queue] ← [Windows Polls] → [OVE Scrape] → [Push Results]
```

## Current Issues

### 1. Windows Scraper Issue (PRIMARY BLOCKER)
**Problem**: Cannot open OVE detail page for VIN W1K6G6DB1SA330253
**Error**: `Unable to open detail page for VIN W1K6G6DB1SA330253`
**Location**: Windows machine browser automation

#### Diagnostic Steps for Windows Machine:

1. **Check OVE Session**:
   - Is the browser logged into OVE?
   - Has the session expired?
   - Try manually searching for VIN W1K6G6DB1SA330253 on OVE

2. **Verify VIN Exists on OVE**:
   - Some VINs may not have detail pages
   - Vehicle might be delisted
   - Could be a private/restricted listing

3. **Check Browser Automation**:
   - Is the correct browser profile being used?
   - Are there popup blockers or captchas?
   - Check if OVE changed their page structure

4. **Debug Commands** (on Windows):
   ```python
   # Test if VIN exists on OVE
   python -c "from scraper import check_vin_exists; print(check_vin_exists('W1K6G6DB1SA330253'))"

   # Test browser navigation manually
   python -c "from scraper import open_ove_detail_page; open_ove_detail_page('W1K6G6DB1SA330253', debug=True)"
   ```

### 2. VPS Observability Issue (MINOR)
**Problem**: `last_polled_at` and `attempts` not updating
**Impact**: Can't track scraper activity from VPS side

## Testing the Full Flow

### Step 1: Check Pending Queue (VPS)
```bash
# See what's in the queue
curl http://localhost:8000/v1/inventory/ove/detail/pending \
  -H "Authorization: Bearer {token}" | jq .
```

### Step 2: Create Test Request (VPS)
```bash
# Use a known-good VIN from OVE
curl -X POST http://localhost:8000/v1/inventory/ove/detail/1C6SRFFP7TN195518/request \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "source_platform": "ADESA",
    "priority": 999,
    "requester": "diagnostic_test"
  }'
```

### Step 3: Monitor Windows Scraper Logs
Look for these log patterns:
- `Checking for pending OVE detail requests` (every 30 seconds)
- `Found X pending OVE detail requests`
- `Processing OVE detail request for VIN: XXX`
- `Deep scrape started for XXX`
- Success: `Deep scrape completed for XXX`
- Failure: `Deep scrape failed for XXX`

### Step 4: Check Request Status (VPS)
```bash
# Check if scraping completed
curl http://localhost:8000/v1/inventory/ove/detail/1C6SRFFP7TN195518 \
  -H "Authorization: Bearer {token}" | jq .status
```

## Quick Fixes

### Fix 1: Clear Stuck Request (VPS)
If W1K6G6DB1SA330253 keeps failing, mark it as failed:
```sql
UPDATE ove_detail_requests
SET status = 'FAILED',
    error_message = 'VIN not accessible on OVE',
    completed_at = NOW()
WHERE vin = 'W1K6G6DB1SA330253'
  AND status = 'PENDING';
```

### Fix 2: Add Polling Telemetry (VPS)
Add endpoint to mark request as being processed:
```python
@router.patch("/detail/{vin}/processing")
def mark_ove_detail_processing(vin: str, db: Session = Depends(get_db)):
    """Windows scraper calls this when it picks up a request"""
    request = db.query(OveDetailRequest).filter_by(vin=vin, status="PENDING").first()
    if request:
        request.last_polled_at = datetime.now(UTC)
        request.attempts += 1
        db.commit()
    return {"status": "marked_processing"}
```

### Fix 3: Windows Scraper VIN Validation
Before attempting scrape, validate VIN exists:
```python
def validate_vin_on_ove(vin):
    """Check if VIN exists on OVE before attempting deep scrape"""
    try:
        # Search for VIN
        search_results = search_ove(vin)
        if not search_results:
            return False, "VIN not found on OVE"

        # Check if detail page is accessible
        if not has_detail_page(vin):
            return False, "VIN has no detail page"

        return True, "VIN is valid"
    except Exception as e:
        return False, str(e)
```

## Recommended Actions

1. **Immediate**: Check why W1K6G6DB1SA330253 can't be accessed on OVE
2. **Short-term**: Add VIN validation before scraping attempts
3. **Medium-term**: Implement polling telemetry endpoints
4. **Long-term**: Add retry logic with exponential backoff

## Success Metrics

- [ ] Windows scraper successfully polls queue every 30 seconds
- [ ] Valid VINs complete scraping within 2 minutes
- [ ] Invalid VINs fail fast with clear error messages
- [ ] VPS tracks polling attempts and last poll time
- [ ] Completed requests contain condition reports and images