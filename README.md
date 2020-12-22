# Automatically Reboot EC2 Instances Gracefully
This is a AWS lambda function that will automatically reboot EC2 instances based on the the memory consumption. This is useful when you have a memory leak on instances that are in a TG (target group), and you need a graceful way to deal with them.

The code is Python, and will use Boto3 to get the healthy instances that are in the specified target groups, and then add them to a list. For each instance, it will check the there are at least 5 or more before continuing. This is a failsafe to prevent taking instances out of the TG when it may adversely affect the ASGs (autoscaling group) ability to handle the load. Once done, it will get the "Memory % Committed Bytes In Use" CloudWatch metric from each one (assuming that it has been enabled on the instance).

Once it has built a list of instances and memory usage, it will select the instance with the highest memory usage, and if it is higher than 65%, it will prepare to reboot that instance.

To do the reboot, it will:

1) Remove the instance from the target groups
2) Wait for an amount of time equal to the target group deregistration delay (wait for draining to complete basically)
3) Reboot the instance
3) Wait 120 seconds
4) Add the instance back into the target groups.

The Lamdba function can be run on a scheuled (even 15 minutes for example) to monitor and remediate hosts with high memory consumption.
