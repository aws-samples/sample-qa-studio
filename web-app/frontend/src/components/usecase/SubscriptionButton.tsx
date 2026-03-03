import React, { useState, useEffect } from 'react';
import Button from "@cloudscape-design/components/button";
import { subscriptionApi, SubscriptionStatusResponse } from '../../utils/api';

interface SubscriptionButtonProps {
  usecaseId: string;
}

const SubscriptionButton: React.FC<SubscriptionButtonProps> = ({ usecaseId }) => {
  const [subscriptionStatus, setSubscriptionStatus] = useState<SubscriptionStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    loadSubscriptionStatus();
  }, [usecaseId]);

  const loadSubscriptionStatus = async () => {
    try {
      setLoading(true);
      const status = await subscriptionApi.getStatus(usecaseId);
      console.log('Subscription status:', status);
      setSubscriptionStatus(status);
    } catch (error) {
      console.error('Error loading subscription status:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubscriptionToggle = async () => {
    if (!subscriptionStatus) return;

    try {
      setActionLoading(true);
      let newStatus: SubscriptionStatusResponse;
      
      if (subscriptionStatus.is_subscribed) {
        newStatus = await subscriptionApi.unsubscribe(usecaseId);
      } else {
        newStatus = await subscriptionApi.subscribe(usecaseId);
      }
      
      // Update status directly from the API response
      setSubscriptionStatus(newStatus);
    } catch (error) {
      console.error('Error toggling subscription:', error);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading || !subscriptionStatus) {
    return (
      <Button disabled loading>
        Loading...
      </Button>
    );
  }

  return (
    <Button
      variant={subscriptionStatus.is_subscribed ? "normal" : "primary"}
      iconName="notification"
      loading={actionLoading}
      onClick={handleSubscriptionToggle}
    >
      {subscriptionStatus.is_subscribed ? 'Unsubscribe' : 'Subscribe to Failures'}
    </Button>
  );
};

export default SubscriptionButton;