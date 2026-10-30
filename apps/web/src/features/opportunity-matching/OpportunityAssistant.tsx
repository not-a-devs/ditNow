import OpportunityMatchingPage from './index';

export interface OpportunityAssistantProps {
  sessionGeneration: string | number;
  onSaved: () => void;
}

/** The authenticated shell owns the session. A replacement unmounts every private draft. */
export default function OpportunityAssistant({ sessionGeneration, onSaved }: OpportunityAssistantProps) {
  return <OpportunityMatchingPage key={sessionGeneration} onSaved={onSaved} />;
}
