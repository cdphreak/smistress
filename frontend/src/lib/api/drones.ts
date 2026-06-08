import { api } from './client';

export interface DroneNotice {
  unit: string;
  line: string;
}

export interface StandingOrders {
  notices: DroneNotice[];
}

export const getStandingOrders = (id: string) =>
  api.get(`/api/profile/${id}/standing-orders`) as Promise<StandingOrders>;
