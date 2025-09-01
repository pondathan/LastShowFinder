# NYC Identification Fix Plan

## Date: 2025-09-01

## Executive Summary

The Last-Show Oracle service has been enhanced with a new Songkick row classification system to improve NYC metro identification, but critical implementation errors are preventing the service from functioning. This plan outlines the issues found and provides a step-by-step approach to fix them.

## Current State Analysis

### What Was Implemented
1. **New Songkick Row Classifier** (`songkick_row_classification.py`)
   - Metro classification via Songkick slug patterns
   - City/state parsing for "Brooklyn, NY" patterns
   - Token fallback for borough names
   - Venue whitelist rescue mechanism
   - Debug logging for NY tokens that don't classify as NYC

2. **Integration into worker.py**
   - Import of new classifier function
   - Updated Songkick scraping to use new classifier
   - Added metro field to Candidate model
   - Precomputed lowercase venue whitelist sets

### What's Working
1. ✅ All tests pass for the new classifier module
2. ✅ Date validation now handles ISO 8601 with timezone info
3. ✅ Service starts and responds to health checks
4. ✅ Venue whitelists load successfully

### What's Broken (Critical Issues)

#### 1. **Missing URL Field in Classifier Return** (CRITICAL)
- **Problem**: `extract_songkick_row_candidate()` returns a dict missing the `url` field
- **Impact**: Candidate creation fails because Candidate model requires `url`
- **Error**: `WARNING:__main__:Failed to parse time tag: 'url'`

#### 2. **Variable Scope Issues** (CRITICAL)
- **Problem**: Debug logging references undefined variables
- **Impact**: Function crashes when trying to log debug information
- **Error**: Variable reference errors in logging

#### 3. **No Fallback Mechanism** (HIGH)
- **Problem**: If new classifier fails, there's no fallback to old parsing logic
- **Impact**: Service returns 0 results when classifier encounters issues
- **Error**: Silent failures with no error recovery

#### 4. **Integration Gaps** (MEDIUM)
- **Problem**: New classifier doesn't handle all edge cases from old system
- **Impact**: Some valid events may be missed
- **Error**: Reduced coverage compared to previous implementation

## Root Cause Analysis

The implementation was rushed and didn't follow proper integration patterns:

1. **Incomplete Return Data**: The new classifier was designed without considering the full Candidate model requirements
2. **Missing Error Handling**: No graceful degradation when the new system fails
3. **Insufficient Testing**: Unit tests passed but integration testing revealed runtime failures
4. **Variable Scoping**: Debug logging was added without proper variable initialization

## Fix Plan

### Phase 1: Critical Bug Fixes (Immediate - 1 hour)

#### 1.1 Fix Missing URL Field
- **File**: `songkick_row_classification.py`
- **Change**: Add `"url": page_url` to return dict in `extract_songkick_row_candidate()`
- **Test**: Verify Candidate creation succeeds

#### 1.2 Fix Variable Scope Issues
- **File**: `songkick_row_classification.py`
- **Change**: Initialize all variables used in debug logging before use
- **Test**: Verify no variable reference errors

#### 1.3 Add Basic Error Handling
- **File**: `worker.py`
- **Change**: Wrap new classifier call in try-catch with fallback to old logic
- **Test**: Verify service doesn't crash on classifier failures

### Phase 2: Integration Improvements (2-3 hours)

#### 2.1 Implement Graceful Fallback
- **File**: `worker.py`
- **Change**: If new classifier returns None or fails, fall back to `extract_row_candidate()`
- **Test**: Verify old functionality is preserved

#### 2.2 Enhanced Error Logging
- **File**: `worker.py`
- **Change**: Add detailed logging for classifier failures and fallback usage
- **Test**: Verify error scenarios are properly logged

#### 2.3 Metro Field Validation
- **File**: `worker.py`
- **Change**: Ensure metro field is properly populated in all Candidate objects
- **Test**: Verify metro classification is working

### Phase 3: Testing & Validation (1-2 hours)

#### 3.1 Integration Testing
- **Test**: Scrape Proxima Parada (known to have NYC shows)
- **Expected**: Should find NYC shows like "Music Hall of Williamsburg, Brooklyn, NY"
- **Validation**: Check metro field is "NYC" for Brooklyn shows

#### 3.2 Regression Testing
- **Test**: Verify SF shows still work correctly
- **Expected**: No degradation in SF metro identification
- **Validation**: Compare results with previous smoke test

#### 3.3 Edge Case Testing
- **Test**: Artists with mixed metro shows
- **Expected**: Proper classification of both NYC and SF shows
- **Validation**: Metro field accuracy

### Phase 4: Performance & Monitoring (1 hour)

#### 4.1 Add Success Metrics
- **File**: `worker.py`
- **Change**: Log classification success rates and fallback usage
- **Goal**: Monitor classifier effectiveness

#### 4.2 Performance Monitoring
- **File**: `worker.py`
- **Change**: Add timing for new vs old classifier paths
- **Goal**: Ensure no performance regression

## Implementation Details

### Fix 1: Complete Return Dict
```python
# In extract_songkick_row_candidate()
return {
    "date_iso": date_iso,
    "metro": metro,
    "city": city,
    "venue": venue,
    "snippet": snippet,
    "source_type": "songkick",
    "source_host": "www.songkick.com",
    "url": page_url,  # ADD THIS
    "notes": "",
}
```

### Fix 2: Graceful Fallback
```python
# In worker.py Songkick scraping
try:
    candidate_data = extract_songkick_row_candidate(
        time_tag, url, SF_VENUE_WHITELIST_LOWER, NYC_VENUE_WHITELIST_LOWER, logger
    )
    if not candidate_data:
        # Fall back to old logic
        candidate_data = extract_row_candidate(time_tag, url, request.artist)
        if candidate_data:
            candidate_data["metro"] = None  # Old logic doesn't classify metro
except Exception as e:
    logger.warning(f"New classifier failed, falling back: {e}")
    candidate_data = extract_row_candidate(time_tag, url, request.artist)
    if candidate_data:
        candidate_data["metro"] = None
```

### Fix 3: Variable Initialization
```python
# In extract_songkick_row_candidate(), before debug logging
venue_text_for_log = ""
for a in row.find_all("a", href=True):
    if "/venues/" in a["href"]:
        venue_text_for_log = a.get_text(" ", strip=True)
        break
```

## Success Criteria

### Immediate (Phase 1)
- [ ] Service starts without errors
- [ ] Songkick scraping returns candidates (not 0 results)
- [ ] No more "Failed to parse time tag: 'url'" errors

### Short-term (Phase 2-3)
- [ ] NYC shows are properly classified (metro="NYC")
- [ ] SF shows continue to work correctly
- [ ] Fallback mechanism preserves old functionality
- [ ] Metro field is populated for all candidates

### Long-term (Phase 4)
- [ ] Classification success rate > 90%
- [ ] Fallback usage < 10%
- [ ] No performance regression
- [ ] Comprehensive logging for monitoring

## Risk Assessment

### Low Risk
- Fixing missing URL field
- Variable scope corrections
- Basic error handling

### Medium Risk
- Fallback mechanism integration
- Metro field validation
- Performance impact

### High Risk
- Breaking existing functionality
- Data loss during transition
- Service downtime

## Rollback Plan

If issues persist after fixes:
1. Comment out new classifier import
2. Revert to old `extract_row_candidate()` calls
3. Remove metro field from Candidate model
4. Restart service with original logic

## Timeline

- **Phase 1**: 1 hour (immediate fixes)
- **Phase 2**: 2-3 hours (integration)
- **Phase 3**: 1-2 hours (testing)
- **Phase 4**: 1 hour (monitoring)
- **Total**: 5-7 hours

## Next Steps

1. **Immediate**: Implement Phase 1 fixes
2. **Today**: Complete Phases 2-3
3. **Tomorrow**: Phase 4 monitoring and validation
4. **Follow-up**: Document lessons learned and improve testing process

## Conclusion

The NYC identification improvements are well-designed but have critical implementation gaps. With focused fixes to the return data structure, error handling, and fallback mechanisms, the service should successfully identify NYC shows that were previously missed while maintaining all existing functionality.

The key is implementing a robust fallback system that ensures the service never returns 0 results due to classifier failures.
