"""
Visitor and User table generators: VISITORS, USERS
"""

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from faker import Faker

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    DataConfig,
    DEVICE_TYPES,
    BROWSERS,
    OS_BY_DEVICE,
    COUNTRIES,
    UTM_SOURCES,
    UTM_MEDIUMS,
    CATEGORIES,
)
from utils import (
    generate_uuid,
    weighted_choice,
    sample_without_replacement,
    random_timestamp,
    random_timestamp_weighted,
    log_normal_value,
    bounded_normal,
    to_array,
    to_object,
)

fake = Faker()
Faker.seed(42)


# =============================================================================
# VISITORS (Anonymous)
# =============================================================================

def generate_visitors(config: DataConfig) -> List[Dict[str, Any]]:
    """
    Generate VISITORS table data.
    
    Visitors are anonymous website visitors before identity resolution.
    Returns list of dicts matching VISITORS schema.
    """
    visitors = []
    
    for i in range(config.num_visitors):
        # Device characteristics
        device_type = weighted_choice(DEVICE_TYPES)
        browser = weighted_choice(BROWSERS)
        os = weighted_choice(OS_BY_DEVICE[device_type])
        country = weighted_choice(COUNTRIES)
        
        # UTM tracking (60% have UTM data)
        has_utm = random.random() < 0.6
        utm_source = weighted_choice(UTM_SOURCES) if has_utm else None
        utm_medium = weighted_choice(UTM_MEDIUMS) if has_utm else None
        utm_campaign = f"campaign_{random.randint(1, 100)}" if has_utm and random.random() < 0.7 else None
        
        # Timestamps
        first_seen = random_timestamp_weighted(
            config.start_date, 
            config.end_date - timedelta(days=30),
            peak_hours=config.peak_hours,
            low_hours=config.low_hours,
        )
        last_seen = random_timestamp(first_seen, config.end_date)
        
        # Location
        if country == "US":
            region = fake.state_abbr()
            city = fake.city()
        elif country == "UK":
            region = random.choice(["England", "Scotland", "Wales", "N. Ireland"])
            city = random.choice(["London", "Manchester", "Birmingham", "Leeds", "Glasgow"])
        elif country == "CA":
            region = random.choice(["ON", "BC", "AB", "QC"])
            city = random.choice(["Toronto", "Vancouver", "Montreal", "Calgary"])
        else:
            region = ""
            city = fake.city()
        
        visitors.append({
            "VISITOR_ID": f"vis_{i:07d}",
            "FIRST_SEEN_TS": first_seen,
            "LAST_SEEN_TS": last_seen,
            "DEVICE_TYPE": device_type,
            "BROWSER": browser,
            "OS": os,
            "COUNTRY": country,
            "REGION": region,
            "CITY": city,
            "UTM_SOURCE": utm_source,
            "UTM_MEDIUM": utm_medium,
            "UTM_CAMPAIGN": utm_campaign,
        })
    
    return visitors


# =============================================================================
# USERS (Identified)
# =============================================================================

def generate_users(
    config: DataConfig,
    visitors: List[Dict[str, Any]],
    households: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Generate USERS table data.
    
    Users are identified visitors who have logged in or created accounts.
    Each user is linked to a visitor (identity resolution) and a household.
    
    Returns list of dicts matching USERS schema.
    """
    users = []
    household_ids = [h["HOUSEHOLD_ID"] for h in households]
    
    # Select which visitors become users (based on identification rate)
    num_users = config.num_users
    identified_visitors = sample_without_replacement(visitors, num_users)
    
    # Track household assignments to respect MEMBER_CNT
    household_members = {h["HOUSEHOLD_ID"]: h["MEMBER_CNT"] for h in households}
    household_current_members = {h["HOUSEHOLD_ID"]: 0 for h in households}
    
    for i, visitor in enumerate(identified_visitors):
        # Find a household with available capacity
        available_households = [
            hh_id for hh_id, max_members in household_members.items()
            if household_current_members[hh_id] < max_members
        ]
        
        if not available_households:
            # Reset and allow overflow
            household_current_members = {h["HOUSEHOLD_ID"]: 0 for h in households}
            available_households = list(household_members.keys())
        
        household_id = random.choice(available_households)
        household_current_members[household_id] += 1
        
        # User creation timestamp (after first visit)
        created_ts = random_timestamp(visitor["FIRST_SEEN_TS"], visitor["LAST_SEEN_TS"])
        updated_ts = random_timestamp(created_ts, config.end_date)
        
        # Email verification (85% verified)
        is_email_verified = random.random() < 0.85
        
        # Subscription status
        subscription_status = weighted_choice({"none": 0.60, "basic": 0.30, "premium": 0.10})
        subscription_start = None
        subscription_end = None
        
        if subscription_status != "none":
            subscription_start = random_timestamp(created_ts, config.end_date - timedelta(days=30)).date()
            # 20% of subscriptions have ended
            if random.random() < 0.2:
                subscription_end = (datetime.combine(subscription_start, datetime.min.time()) + 
                                   timedelta(days=random.randint(30, 365))).date()
        
        # Lifetime value (power-law distribution)
        ltv = log_normal_value(median=150, sigma=1.0)
        ltv = max(0, min(50000, ltv))
        
        # Login count
        login_cnt = int(log_normal_value(median=5, sigma=0.8))
        login_cnt = max(1, min(500, login_cnt))
        
        # Interests (ARRAY) - categories they've shown interest in
        num_interests = random.choices([0, 1, 2, 3, 4, 5], weights=[5, 15, 30, 30, 15, 5])[0]
        interest_categories = sample_without_replacement(
            [cat["name"] for cat in CATEGORIES], 
            num_interests
        )
        
        # Preferences (OBJECT)
        preferences = {
            "newsletter": random.random() < 0.65,
            "sms_opt_in": random.random() < 0.25,
            "preferred_currency": "USD",
            "dark_mode": random.random() < 0.40,
            "language": "en",
        }
        
        # Address (70% have address)
        has_address = random.random() < 0.70
        
        first_name = fake.first_name()
        last_name = fake.last_name()
        
        users.append({
            "USER_ID": f"usr_{i:06d}",
            "VISITOR_ID": visitor["VISITOR_ID"],
            "HOUSEHOLD_ID": household_id,
            "EMAIL": f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 999)}@{fake.free_email_domain()}",
            "FIRST_NAME": first_name,
            "LAST_NAME": last_name,
            "PHONE": fake.phone_number() if random.random() < 0.80 else None,
            "CREATED_TS": created_ts,
            "UPDATED_TS": updated_ts,
            "IS_EMAIL_VERIFIED": is_email_verified,
            "SUBSCRIPTION_STATUS": subscription_status,
            "SUBSCRIPTION_START_DT": subscription_start,
            "SUBSCRIPTION_END_DT": subscription_end,
            "LIFETIME_VALUE_SUM": round(ltv, 2),
            "LOGIN_CNT": login_cnt,
            "INTERESTS": to_array(interest_categories),
            "PREFERENCES": to_object(preferences),
            "ADDRESS_STREET": fake.street_address() if has_address else None,
            "ADDRESS_CITY": visitor["CITY"] if has_address else None,
            "ADDRESS_STATE": visitor["REGION"] if has_address else None,
            "ADDRESS_POSTAL_CODE": fake.postcode() if has_address else None,
            "ADDRESS_COUNTRY": visitor["COUNTRY"] if has_address else None,
        })
    
    return users
