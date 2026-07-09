# RETINA API Connection Testing Improvements

## Summary

Added comprehensive connection testing and error diagnostics to make it easier to configure API integrations in RETINA.

## What Changed

### 1. New Test Connection API Endpoint (`POST /api/connectors/test`)

Tests connector credentials without saving them to the database.

**Request:**
```json
{
  "connector_type": "github",
  "credentials": {
    "token": "ghp_xxx",
    "org": "myorg"
  },
  "base_url": "https://api.github.com"
}
```

**Success Response:**
```json
{
  "success": true,
  "message": "Successfully connected and retrieved 42 user(s)",
  "user_count": 42,
  "sample_user": {
    "id": "123",
    "email": "user@example.com",
    "name": "John Doe"
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "category": "auth",
  "title": "Authentication Failed",
  "message": "The API rejected your credentials (401 Unauthorized)",
  "suggestions": [
    "Verify your API token/key is correct and not expired",
    "Check if the token has been regenerated or revoked",
    "Ensure you're using the correct authentication format"
  ],
  "raw_error": "HTTPStatusError: 401 Unauthorized"
}
```

### 2. Error Diagnosis System

Added `diagnose_connector_error()` function that categorizes errors into:

- **network** - Connection/timeout errors
- **auth** - 401 Unauthorized errors
- **permissions** - 403 Forbidden errors
- **endpoint** - 404 Not Found errors
- **server** - 5xx server errors
- **rate_limit** - Rate limiting errors
- **unknown** - Uncategorized errors

Each category includes:
- **title** - Short error description
- **message** - Human-readable explanation
- **suggestions** - Actionable steps to fix the issue

### 3. UI Enhancements

#### Test Connection Button
- Added "Test Connection" button in both Add and Edit application modals
- Shows real-time feedback while testing
- Displays detailed error information with suggestions
- Shows sample user data on success

#### Visual Feedback
- **Success**: Green box with checkmark and user count
- **Error**: Red box with:
  - Error title and description
  - Bulleted list of suggestions
  - Collapsible technical details section

#### Improved Sync Errors
- Sync failures now show diagnostic information
- Multi-line alert with categorized error and suggestions
- Helps distinguish between credential issues, endpoint problems, and permissions

## Benefits

### Before
- Save credentials → Sync → Get vague error → Guess what's wrong
- No way to test without saving
- Generic error: "Sync failed: HTTPStatusError: 401"

### After
- Test Connection → Get specific diagnosis → Fix issue → Save
- Clear categorization of error types
- Actionable suggestions for each error category
- Sample data preview on successful test

## Example Error Messages

### Authentication Error
```
✗ Authentication Failed

The API rejected your credentials (401 Unauthorized)

Suggestions:
• Verify your API token/key is correct and not expired
• Check if the token has been regenerated or revoked
• Ensure you're using the correct authentication format

[Technical details ▼]
```

### Permission Error
```
✗ Permission Denied

Your credentials lack required permissions (403 Forbidden)

Suggestions:
• Verify the API token has the necessary scopes/permissions
• Check if your account has admin access if required
• Review the connector documentation for required permissions

[Technical details ▼]
```

### Endpoint Error
```
✗ Resource Not Found

The API endpoint was not found (404): /orgs/wrongorg/members

Suggestions:
• Verify the base URL points to the correct API version
• Check if organization/domain name in credentials is correct
• Ensure the resource (org, workspace, etc.) exists

[Technical details ▼]
```

### Network Error
```
✗ Connection Failed

Could not reach the API endpoint: Connection timeout

Suggestions:
• Verify the base URL is correct
• Check if the service is currently available
• Ensure your network allows outbound connections to this service

[Technical details ▼]
```

## Usage

### Testing Before Save
1. Select a connector in the Add Application modal
2. Fill in credentials
3. Click "Test Connection"
4. Review the result:
   - **Success**: Proceed to save
   - **Error**: Follow suggestions and test again

### Testing Existing Configuration
1. Click "Edit" on any application
2. Modify credentials or base URL if needed
3. Click "Test Connection" to verify
4. Update if test passes

### Debugging Sync Failures
When a sync fails:
1. Check the error alert for diagnosis
2. Follow the suggestions
3. Edit the application
4. Test the connection
5. Save and retry sync

## Technical Notes

- Uses `httpx` exception types for precise error categorization
- Leverages HTTP status codes (401, 403, 404, 5xx) for intelligent diagnosis
- Test endpoint doesn't modify database state
- Sync endpoint now uses same diagnostic system for consistency
- All connectors inherit the error handling automatically
