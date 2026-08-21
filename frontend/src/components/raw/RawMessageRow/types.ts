/** Tell the list a sighting is gone, so the row stops advertising it. */
export type DropEvent = (messageId: number, eventId: number) => void;
