Output assets/demo/instascript-demo-advanced.gif

Set Shell "bash"
Set FontSize 18
Set Width 1200
Set Height 750
Set FontFamily "JetBrainsMono Nerd Font"
Set Theme "Dracula"
Set Padding 24
Set WindowBar Colorful
Set CursorBlink false
Set TypingSpeed 25ms
Set Framerate 10
Set WaitTimeout 90s

# Clean prompt off-screen
Hide
Type "export PS1='$ '"
Enter
Type "cd ~/Projects/instaScript"
Enter
Type "rm -rf ~/ig_intel/Inbox/*"
Enter
Show

Type "bin/instascript 'https://www.instagram.com/reel/Da-4TGWMffZ/' --review"
Enter
Sleep 35s

Type "ls -la ~/ig_intel/Inbox/video-by-go-micro/"
Enter
Sleep 3s

Type "cat ~/ig_intel/Inbox/video-by-go-micro/summary.md"
Enter
Sleep 4s

Type "cat ~/ig_intel/Inbox/video-by-go-micro/flags.md"
Enter
Sleep 5s

Type "echo 'DONE! Pipeline complete with transcription and AI review.'"
Enter
Sleep 3s
