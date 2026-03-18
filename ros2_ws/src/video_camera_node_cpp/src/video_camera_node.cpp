// ============================================================================
// Video Camera Node — reads frames from a video file and publishes them
// as sensor_msgs/Image on /camera/image_raw at ~10 FPS.
// ============================================================================

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <std_msgs/msg/header.hpp>
#include <cv_bridge/cv_bridge.h>
#include <opencv2/opencv.hpp>
#include <filesystem>
#include <unordered_map>
#include <vector>
#include <algorithm>

class VideoCameraNode : public rclcpp::Node
{
public:
    VideoCameraNode() : Node("video_camera_node")
    {
        // ── Declare parameters: video file or frames dir, label dir, and fps ─
        this->declare_parameter<std::string>("video_path", "test.mp4");
        this->declare_parameter<std::string>("frames_dir", "");
        this->declare_parameter<std::string>("label_dir", "");
        this->declare_parameter<double>("fps", 10.0);

        std::string video_path = this->get_parameter("video_path").as_string();
        std::string frames_dir = this->get_parameter("frames_dir").as_string();
        label_dir_ = this->get_parameter("label_dir").as_string();
        double fps = this->get_parameter("fps").as_double();

        fps_ = std::max(1.0, fps);

        // ── Create publishers ──────────────────────────────────────────────
        publisher_ = this->create_publisher<sensor_msgs::msg::Image>("/camera/image_raw", 10);
        gt_publisher_ = this->create_publisher<sensor_msgs::msg::Image>("/camera/gt_image_raw", 10);

        // ── If frames_dir provided, load image list ────────────────────────
        use_frames_dir_ = false;
        if (!frames_dir.empty()) {
            try {
                for (const auto &entry : std::filesystem::directory_iterator(frames_dir)) {
                    if (!entry.is_regular_file()) continue;
                    auto ext = entry.path().extension().string();
                    std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);
                    if (ext == ".png" || ext == ".jpg" || ext == ".jpeg") {
                        frame_paths_.push_back(entry.path().string());
                    }
                }
                std::sort(frame_paths_.begin(), frame_paths_.end());
                if (!frame_paths_.empty()) {
                    use_frames_dir_ = true;
                    RCLCPP_INFO(this->get_logger(), "Publishing frames from directory: %s (count=%zu)", frames_dir.c_str(), frame_paths_.size());
                }
            } catch (const std::exception &e) {
                RCLCPP_WARN(this->get_logger(), "Error reading frames_dir '%s': %s", frames_dir.c_str(), e.what());
            }
        }

        // ── If label_dir provided, build basename -> fullpath map once (for GT frames)
        if (!label_dir_.empty()) {
            try {
                for (const auto &entry : std::filesystem::directory_iterator(label_dir_)) {
                    if (!entry.is_regular_file()) continue;
                    auto stem = entry.path().stem().string();
                    gt_map_[stem] = entry.path().string();
                }
                if (!gt_map_.empty()) {
                    RCLCPP_INFO(this->get_logger(), "Loaded %zu GT labels from %s", gt_map_.size(), label_dir_.c_str());
                }
            } catch (const std::exception &e) {
                RCLCPP_WARN(this->get_logger(), "Error indexing label_dir '%s': %s", label_dir_.c_str(), e.what());
            }
        }

        // ── If not using frames dir, fall back to video file
        if (!use_frames_dir_) {
            cap_.open(video_path);
            if (!cap_.isOpened()) {
                RCLCPP_ERROR(this->get_logger(), "Cannot open video file: %s", video_path.c_str());
                rclcpp::shutdown();
                return;
            }
            RCLCPP_INFO(this->get_logger(), "Opened video: %s", video_path.c_str());
        }

        // ── Timer callback at configured FPS
        int period_ms = static_cast<int>(1000.0 / fps_);
        timer_ = this->create_wall_timer(std::chrono::milliseconds(period_ms), std::bind(&VideoCameraNode::timer_callback, this));
    }

private:
    void timer_callback()
    {
        // Wait for at least one subscriber before publishing frames
        if (publisher_->get_subscription_count() == 0 && gt_publisher_->get_subscription_count() == 0) {
            if (!waiting_logged_) {
                RCLCPP_INFO(this->get_logger(), "Waiting for subscribers on /camera/image_raw or /camera/gt_image_raw ...");
                waiting_logged_ = true;
            }
            return;
        }

        cv::Mat frame;

        if (use_frames_dir_) {
            if (frame_idx_ >= frame_paths_.size()) {
                RCLCPP_INFO(this->get_logger(), "Frames finished — shutting down.");
                timer_->cancel();
                rclcpp::shutdown();
                return;
            }
            frame = cv::imread(frame_paths_[frame_idx_], cv::IMREAD_COLOR);
        } else {
            cap_ >> frame;
        }

        // If video/frames end, shut down gracefully
        if (frame.empty()) {
            RCLCPP_INFO(this->get_logger(), "Video/frames ended — shutting down.");
            timer_->cancel();
            rclcpp::shutdown();
            return;
        }

        // Convert OpenCV image (BGR) to ROS2 Image message
        auto msg = cv_bridge::CvImage(std_msgs::msg::Header(), "bgr8", frame).toImageMsg();
        msg->header.stamp = this->now();
        msg->header.frame_id = "camera_frame";
        publisher_->publish(*msg);

        // Publish GT image if available (matching basename in label_dir_)
        if (!label_dir_.empty() && !gt_map_.empty() && use_frames_dir_) {
            std::string basename = std::filesystem::path(frame_paths_[frame_idx_]).stem().string();
            auto it = gt_map_.find(basename);
            if (it != gt_map_.end()) {
                cv::Mat gt = cv::imread(it->second, cv::IMREAD_UNCHANGED);
                if (!gt.empty()) {
                    cv::Mat gt_bgr;
                    if (gt.channels() == 1) cv::cvtColor(gt, gt_bgr, cv::COLOR_GRAY2BGR);
                    else if (gt.channels() == 4) cv::cvtColor(gt, gt_bgr, cv::COLOR_BGRA2BGR);
                    else gt_bgr = gt;

                    auto gt_msg = cv_bridge::CvImage(std_msgs::msg::Header(), "bgr8", gt_bgr).toImageMsg();
                    gt_msg->header.stamp = msg->header.stamp;
                    gt_msg->header.frame_id = "camera_frame";
                    gt_publisher_->publish(*gt_msg);
                }
            }
        }

        if (use_frames_dir_) frame_idx_++;
    }

    // ── Member variables ───────────────────────────────────────────────────
    cv::VideoCapture cap_;
    rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr publisher_;
    rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr gt_publisher_;
    rclcpp::TimerBase::SharedPtr timer_;
    bool waiting_logged_ = false;
    bool use_frames_dir_ = false;
    double fps_ = 10.0;
    std::vector<std::string> frame_paths_;
    size_t frame_idx_ = 0;
    std::string label_dir_;
    std::unordered_map<std::string, std::string> gt_map_;  // basename -> full path
};

// ── Main ───────────────────────────────────────────────────────────────────
int main(int argc, char *argv[])
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<VideoCameraNode>());
    rclcpp::shutdown();
    return 0;
}
