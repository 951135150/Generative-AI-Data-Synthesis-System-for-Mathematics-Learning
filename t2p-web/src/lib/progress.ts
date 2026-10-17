export function getCourseGrade(masteryPercent: number): string {
  if (masteryPercent >= 97) return 'A+';
  if (masteryPercent >= 93) return 'A';
  if (masteryPercent >= 90) return 'A−';
  if (masteryPercent >= 87) return 'B+';
  if (masteryPercent >= 83) return 'B';
  if (masteryPercent >= 80) return 'B−';
  if (masteryPercent >= 77) return 'C+';
  if (masteryPercent >= 73) return 'C';
  if (masteryPercent >= 70) return 'C−';
  if (masteryPercent >= 67) return 'D+';
  if (masteryPercent >= 63) return 'D';
  if (masteryPercent >= 60) return 'D−';
  return 'F';
}

export function getAcademicStanding(masteryPercent: number): string {
  if (masteryPercent >= 90) return 'Advanced';
  if (masteryPercent >= 75) return 'Proficient';
  if (masteryPercent >= 50) return 'Developing';
  return 'Foundation';
}

export interface LearningBrief {
  title: string;
  description: string;
}

export function getLearningBrief(
  masteryPercent: number,
  strongestTopic: string,
  weakestTopic: string,
): LearningBrief {
  if (masteryPercent >= 90) {
    return {
      title: 'Consolidate advanced transfer.',
      description: `Your overall record supports more demanding transfer problems. Maintain ${strongestTopic} while using exam mode to test independent reasoning across less familiar domains.`,
    };
  }
  if (masteryPercent >= 75) {
    return {
      title: 'Convert procedural strength into balanced mastery.',
      description: `Your record is proficient overall, with the strongest evidence in ${strongestTopic}. Prioritize ${weakestTopic} to improve transfer beyond familiar procedures.`,
    };
  }
  return {
    title: 'Build depth through deliberate practice.',
    description: `Continue with targeted drill mode. Review mentor feedback after every submission and revisit ${weakestTopic}, the weakest recorded topic.`,
  };
}

export function formatStudyTime(totalMinutes: number): string {
  const safeMinutes = Math.max(0, Number.isFinite(totalMinutes) ? totalMinutes : 0);
  if (safeMinutes < 60) return `${Math.round(safeMinutes)} min`;
  const hours = safeMinutes / 60;
  return `${Number.isInteger(hours) ? hours.toFixed(0) : hours.toFixed(1)} h`;
}

interface MasteryDomainDefinition {
  domain: string;
  topics: readonly string[];
}

export interface DomainMastery {
  domain: string;
  mastery: number;
  topicCount: number;
  topics: string[];
}

const MASTERY_DOMAINS: readonly MasteryDomainDefinition[] = [
  {
    domain: 'Foundations',
    topics: ['Limits and Continuity'],
  },
  {
    domain: 'Differential',
    topics: ['Derivatives and Differentiation', 'Applications of Derivatives'],
  },
  {
    domain: 'Integral',
    topics: [
      'Integration and FTOC',
      'Indefinite Integrals',
      'Applications of Integration',
      'Techniques of Integration',
    ],
  },
  {
    domain: 'Multivariable',
    topics: ['Multivariable Calculus', 'Multiple Integrals', 'Vector Calculus'],
  },
  {
    domain: 'Series & Curves',
    topics: ['Sequences and Series', 'Parametric and Polar Curves'],
  },
  {
    domain: 'Diff. Equations',
    topics: ['Differential Equations'],
  },
];

const TOPIC_CHART_LABELS: Record<string, string> = {
  'Limits and Continuity': 'Limits',
  'Derivatives and Differentiation': 'Derivatives',
  'Integration and FTOC': 'FTOC',
  'Multivariable Calculus': 'Multivariable',
  'Applications of Derivatives': 'Derivative Apps',
  'Indefinite Integrals': 'Antiderivatives',
  'Applications of Integration': 'Integral Apps',
  'Multiple Integrals': 'Multiple Integrals',
  'Vector Calculus': 'Vector Calculus',
  'Sequences and Series': 'Series',
  'Differential Equations': 'Diff. Equations',
  'Techniques of Integration': 'Integration Tech.',
  'Parametric and Polar Curves': 'Parametric/Polar',
};

export function aggregateMasteryDomains(
  topicMastery: Record<string, number>,
): DomainMastery[] {
  return MASTERY_DOMAINS.map(({ domain, topics }) => {
    const recordedTopics = topics.filter((topic) => (
      Object.prototype.hasOwnProperty.call(topicMastery, topic)
    ));
    if (recordedTopics.length === 0) return null;
    const total = recordedTopics.reduce((sum, topic) => {
      const rawScore = topicMastery[topic];
      const score = Number.isFinite(rawScore) ? Math.min(1, Math.max(0, rawScore)) : 0;
      return sum + score;
    }, 0);
    return {
      domain,
      mastery: Math.round(total / recordedTopics.length * 100),
      topicCount: recordedTopics.length,
      topics: recordedTopics,
    };
  }).filter((domain): domain is DomainMastery => domain !== null);
}

export function getTopicChartLabel(topic: string): string {
  if (TOPIC_CHART_LABELS[topic]) return TOPIC_CHART_LABELS[topic];
  return topic.length > 18 ? `${topic.slice(0, 18)}…` : topic;
}
