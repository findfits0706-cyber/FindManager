import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { failed: boolean };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled frontend render error", error.name, info.componentStack);
  }

  render() {
    if (this.state.failed) {
      return (
        <main className="standalone-error" role="alert">
          <h1>画面を表示できませんでした</h1>
          <p>一時的な問題が発生しました。ページを再読み込みしてください。</p>
          <button type="button" onClick={() => window.location.reload()}>
            再読み込み
          </button>
        </main>
      );
    }
    return this.props.children;
  }
}
