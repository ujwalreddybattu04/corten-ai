"use client";

interface RelatedQuestionsProps {
    questions: string[];
    onSelect: (question: string) => void;
}

export default function RelatedQuestions({ questions, onSelect }: RelatedQuestionsProps) {
    if (!questions || questions.length === 0) return null;

    return (
        <div className="related-questions" id="related-questions">
            <h3 className="related-questions-title">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" /><path d="M12 17h.01" />
                </svg>
                Related
            </h3>
            <div className="related-questions-list">
                {questions.map((q, i) => (
                    <button
                        key={i}
                        className="related-question-btn"
                        onClick={() => onSelect(q)}
                        id={`related-q-${i}`}
                    >
                        <span className="related-question-text">{q}</span>
                        <svg
                            className="related-question-arrow"
                            xmlns="http://www.w3.org/2000/svg"
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                        >
                            <line x1="5" y1="12" x2="19" y2="12" />
                            <polyline points="12 5 19 12 12 19" />
                        </svg>
                    </button>
                ))}
            </div>
        </div>
    );
}
